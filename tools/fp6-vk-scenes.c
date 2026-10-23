/* Offscreen Vulkan scene runner for the FP6 GPU bring-up. Each scene renders a
 * 64x64 RGBA8 image and copies it to a host buffer. Two uses:
 *
 *  - Under the freedreno noop drm-shim with FD_RD_DUMP=enable,full it makes Mesa
 *    Turnip emit the exact A810 command stream for the scene (nothing executes).
 *  - On a real software driver (lavapipe) it renders for real, printing a 16x16
 *    sampled grid of the result as the independent pixel reference and writing a
 *    PPM, so the phone's output can be compared against something that is not the
 *    GPU under test.
 *
 *   glslangValidator -V <scene>.vert -o <scene>.vert.spv   (and .frag)
 *   fp6-vk-scenes SCENE DIR [out.ppm]
 *
 * SCENE: flat varying ubo blend depth texture vertexbuf. DIR holds SCENE.vert.spv
 * and SCENE.frag.spv. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define CHECK(x) do { VkResult r_ = (x); if (r_ != VK_SUCCESS) { \
	fprintf(stderr, "%s failed: %d (line %d)\n", #x, r_, __LINE__); exit(1); } } while (0)
#define W 64
#define H 64

static VkPhysicalDevice pd;
static VkDevice dev;

static uint32_t *load(const char *path, size_t *size)
{
	FILE *f = fopen(path, "rb");
	if (!f) { perror(path); exit(1); }
	fseek(f, 0, SEEK_END);
	*size = (size_t)ftell(f);
	rewind(f);
	uint32_t *data = malloc(*size);
	if (fread(data, 1, *size, f) != *size) exit(1);
	fclose(f);
	return data;
}

static uint32_t memtype(uint32_t bits, VkMemoryPropertyFlags want)
{
	VkPhysicalDeviceMemoryProperties mp;
	vkGetPhysicalDeviceMemoryProperties(pd, &mp);
	for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
		if ((bits & (1u << i)) && (mp.memoryTypes[i].propertyFlags & want) == want) return i;
	fprintf(stderr, "no memory type\n");
	exit(1);
}

static VkShaderModule module(const char *dir, const char *scene, const char *stage)
{
	char path[512];
	snprintf(path, sizeof path, "%s/%s.%s.spv", dir, scene, stage);
	size_t size;
	uint32_t *code = load(path, &size);
	VkShaderModuleCreateInfo ci = { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, 0, 0, size, code };
	VkShaderModule m;
	CHECK(vkCreateShaderModule(dev, &ci, 0, &m));
	return m;
}

struct buf { VkBuffer b; VkDeviceMemory m; void *map; };

static struct buf make_buffer(VkDeviceSize size, VkBufferUsageFlags usage)
{
	struct buf r;
	VkBufferCreateInfo bci = { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, 0, 0, size, usage };
	CHECK(vkCreateBuffer(dev, &bci, 0, &r.b));
	VkMemoryRequirements mr;
	vkGetBufferMemoryRequirements(dev, r.b, &mr);
	VkMemoryAllocateInfo mai = { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, 0, mr.size,
	    memtype(mr.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) };
	CHECK(vkAllocateMemory(dev, &mai, 0, &r.m));
	CHECK(vkBindBufferMemory(dev, r.b, r.m, 0));
	CHECK(vkMapMemory(dev, r.m, 0, size, 0, &r.map));
	return r;
}

struct image { VkImage i; VkDeviceMemory m; VkImageView v; };


static struct image make_image_t(VkFormat fmt, unsigned w, unsigned h, VkImageUsageFlags usage,
    VkImageAspectFlags aspect, VkImageTiling tiling)
{
	struct image r;
	VkImageCreateInfo ic = { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
	ic.imageType = VK_IMAGE_TYPE_2D; ic.format = fmt; ic.extent = (VkExtent3D){ w, h, 1 };
	ic.mipLevels = 1; ic.arrayLayers = 1; ic.samples = VK_SAMPLE_COUNT_1_BIT;
	ic.tiling = tiling; ic.usage = usage;
	ic.initialLayout = tiling == VK_IMAGE_TILING_LINEAR ? VK_IMAGE_LAYOUT_PREINITIALIZED : VK_IMAGE_LAYOUT_UNDEFINED;
	CHECK(vkCreateImage(dev, &ic, 0, &r.i));
	VkMemoryRequirements mr;
	vkGetImageMemoryRequirements(dev, r.i, &mr);
	VkMemoryAllocateInfo mai = { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, 0, mr.size, memtype(mr.memoryTypeBits,
	    tiling == VK_IMAGE_TILING_LINEAR ? VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT : 0) };
	CHECK(vkAllocateMemory(dev, &mai, 0, &r.m));
	CHECK(vkBindImageMemory(dev, r.i, r.m, 0));
	VkImageViewCreateInfo vc = { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO };
	vc.image = r.i; vc.viewType = VK_IMAGE_VIEW_TYPE_2D; vc.format = fmt;
	vc.subresourceRange = (VkImageSubresourceRange){ aspect, 0, 1, 0, 1 };
	CHECK(vkCreateImageView(dev, &vc, 0, &r.v));
	return r;
}

static struct image make_image(VkFormat fmt, unsigned w, unsigned h, VkImageUsageFlags usage,
    VkImageAspectFlags aspect)
{
	return make_image_t(fmt, w, h, usage, aspect, VK_IMAGE_TILING_OPTIMAL);
}

static void barrier(VkCommandBuffer cmd, VkImage img, VkImageAspectFlags aspect, VkImageLayout from,
    VkImageLayout to, VkAccessFlags src, VkAccessFlags dst, VkPipelineStageFlags ss, VkPipelineStageFlags ds)
{
	VkImageMemoryBarrier b = { VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, 0, src, dst, from, to,
	    VK_QUEUE_FAMILY_IGNORED, VK_QUEUE_FAMILY_IGNORED, img, { aspect, 0, 1, 0, 1 } };
	vkCmdPipelineBarrier(cmd, ss, ds, 0, 0, 0, 0, 0, 1, &b);
}

int main(int argc, char **argv)
{
	if (argc < 3) { fprintf(stderr, "usage: %s SCENE DIR [out.ppm]\n", argv[0]); return 2; }
	const char *scene = argv[1], *dir = argv[2];
	int is_flat = !strcmp(scene, "flat"), is_varying = !strcmp(scene, "varying"), is_ubo = !strcmp(scene, "ubo"),
	    is_blend = !strcmp(scene, "blend"), is_depth = !strcmp(scene, "depth"),
	    is_texture = !strcmp(scene, "texture"), is_vbuf = !strcmp(scene, "vertexbuf");
	/* Diagnostics that split the vertexbuf and texture scenes into their parts: vertex fetch
	 * without an index buffer, index fetch without a vertex buffer, and a host-written linear
	 * texture without the staging upload. They reuse the shaders of the scene they reduce. */
	int is_vbufdraw = !strcmp(scene, "vbufdraw"), is_idxonly = !strcmp(scene, "idxonly"),
	    is_texlinear = !strcmp(scene, "texlinear");
	const char *shader = is_vbufdraw ? "vertexbuf" : is_idxonly ? "flat" : is_texlinear ? "texture" : scene;
	if (!(is_flat || is_varying || is_ubo || is_blend || is_depth || is_texture || is_vbuf || is_vbufdraw ||
	      is_idxonly || is_texlinear)) {
		fprintf(stderr, "unknown scene %s\n", scene);
		return 2;
	}
	VkApplicationInfo app = { VK_STRUCTURE_TYPE_APPLICATION_INFO, 0, "fp6-vk-scenes", 1, "none", 1, VK_API_VERSION_1_1 };
	VkInstanceCreateInfo ici = { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, 0, 0, &app };
	VkInstance inst;
	CHECK(vkCreateInstance(&ici, 0, &inst));
	uint32_t n = 1;
	VkResult e = vkEnumeratePhysicalDevices(inst, &n, &pd);
	if ((e != VK_SUCCESS && e != VK_INCOMPLETE) || n < 1) { fprintf(stderr, "no device\n"); return 1; }
	VkPhysicalDeviceProperties props;
	vkGetPhysicalDeviceProperties(pd, &props);
	printf("device: %s\n", props.deviceName);
	float prio = 1.0f;
	VkDeviceQueueCreateInfo qci = { VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, 0, 0, 0, 1, &prio };
	VkDeviceCreateInfo dci = { VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, 0, 0, 1, &qci };
	CHECK(vkCreateDevice(pd, &dci, 0, &dev));
	VkQueue queue;
	vkGetDeviceQueue(dev, 0, 0, &queue);

	struct image color = make_image(VK_FORMAT_R8G8B8A8_UNORM, W, H,
	    VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT, VK_IMAGE_ASPECT_COLOR_BIT);
	struct image depth = { 0 };
	if (is_depth)
		depth = make_image(VK_FORMAT_D32_SFLOAT, W, H, VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT,
		    VK_IMAGE_ASPECT_DEPTH_BIT);
	struct buf readback = make_buffer(W * H * 4, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
	/* A sentinel marks the result buffer in a capture; the render covers every texel. */
	memset(readback.map, 0xa5, W * H * 4);

	/* Render pass: colour (+ depth). */
	VkAttachmentDescription att[2] = {
		{ 0, VK_FORMAT_R8G8B8A8_UNORM, VK_SAMPLE_COUNT_1_BIT, VK_ATTACHMENT_LOAD_OP_CLEAR,
		  VK_ATTACHMENT_STORE_OP_STORE, VK_ATTACHMENT_LOAD_OP_DONT_CARE, VK_ATTACHMENT_STORE_OP_DONT_CARE,
		  VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL },
		{ 0, VK_FORMAT_D32_SFLOAT, VK_SAMPLE_COUNT_1_BIT, VK_ATTACHMENT_LOAD_OP_CLEAR,
		  VK_ATTACHMENT_STORE_OP_DONT_CARE, VK_ATTACHMENT_LOAD_OP_DONT_CARE, VK_ATTACHMENT_STORE_OP_DONT_CARE,
		  VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL },
	};
	VkAttachmentReference cref = { 0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL };
	VkAttachmentReference dref = { 1, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL };
	VkSubpassDescription sub = { 0, VK_PIPELINE_BIND_POINT_GRAPHICS, 0, 0, 1, &cref, 0, is_depth ? &dref : 0 };
	VkRenderPassCreateInfo rpci = { VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO, 0, 0, is_depth ? 2u : 1u, att, 1, &sub };
	VkRenderPass rp;
	CHECK(vkCreateRenderPass(dev, &rpci, 0, &rp));
	VkImageView views[2] = { color.v, depth.v };
	VkFramebufferCreateInfo fci = { VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO, 0, 0, rp, is_depth ? 2u : 1u, views, W, H, 1 };
	VkFramebuffer fb;
	CHECK(vkCreateFramebuffer(dev, &fci, 0, &fb));

	/* Per-scene resources. */
	struct buf ubo = { 0 }, vbuf = { 0 }, ibuf = { 0 }, staging = { 0 };
	struct image tex = { 0 };
	VkSampler sampler = 0;
	if (is_ubo) {
		ubo = make_buffer(16, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT);
		float c[4] = { 0.2f, 0.8f, 0.4f, 1.0f };
		memcpy(ubo.map, c, sizeof c);
	}
	if (is_vbufdraw) {
		/* the quad's six vertices expanded, drawn without an index buffer */
		float q[4][5] = { { -0.6f, -0.6f, 1, 0, 0 }, { 0.6f, -0.6f, 0, 1, 0 },
		    { 0.6f, 0.6f, 0, 0, 1 }, { -0.6f, 0.6f, 1, 1, 0 } };
		int order[6] = { 0, 1, 2, 0, 2, 3 };
		float v[6][5];
		for (int i = 0; i < 6; i++) memcpy(v[i], q[order[i]], sizeof v[i]);
		vbuf = make_buffer(sizeof v, VK_BUFFER_USAGE_VERTEX_BUFFER_BIT);
		memcpy(vbuf.map, v, sizeof v);
	}
	if (is_idxonly) {
		uint16_t idx[3] = { 0, 1, 2 };
		ibuf = make_buffer(sizeof idx, VK_BUFFER_USAGE_INDEX_BUFFER_BIT);
		memcpy(ibuf.map, idx, sizeof idx);
	}
	if (is_vbuf) {
		/* position.xy, colour.rgb per vertex; a quad as two triangles by index */
		float v[4][5] = { { -0.6f, -0.6f, 1, 0, 0 }, { 0.6f, -0.6f, 0, 1, 0 },
		    { 0.6f, 0.6f, 0, 0, 1 }, { -0.6f, 0.6f, 1, 1, 0 } };
		uint16_t idx[6] = { 0, 1, 2, 0, 2, 3 };
		vbuf = make_buffer(sizeof v, VK_BUFFER_USAGE_VERTEX_BUFFER_BIT);
		memcpy(vbuf.map, v, sizeof v);
		ibuf = make_buffer(sizeof idx, VK_BUFFER_USAGE_INDEX_BUFFER_BIT);
		memcpy(ibuf.map, idx, sizeof idx);
	}
	if (is_texlinear) {
		uint32_t texels[16];
		for (int y = 0; y < 4; y++)
			for (int x = 0; x < 4; x++)
				texels[y * 4 + x] = ((x + y) & 1) ? 0xff00ff00u : 0xff0000ffu;
		tex = make_image_t(VK_FORMAT_R8G8B8A8_UNORM, 4, 4, VK_IMAGE_USAGE_SAMPLED_BIT,
		    VK_IMAGE_ASPECT_COLOR_BIT, VK_IMAGE_TILING_LINEAR);
		VkImageSubresource sr = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0 };
		VkSubresourceLayout sl;
		vkGetImageSubresourceLayout(dev, tex.i, &sr, &sl);
		void *map;
		CHECK(vkMapMemory(dev, tex.m, 0, VK_WHOLE_SIZE, 0, &map));
		for (int y = 0; y < 4; y++) memcpy((char *)map + sl.offset + y * sl.rowPitch, &texels[y * 4], 16);
		vkUnmapMemory(dev, tex.m);
	}
	if (is_texture || is_texlinear) {
		/* sampler shared by both texture scenes */
		VkSamplerCreateInfo sc = { VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO };
		sc.magFilter = VK_FILTER_NEAREST; sc.minFilter = VK_FILTER_NEAREST;
		sc.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
		sc.addressModeU = sc.addressModeV = sc.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
		sc.maxLod = 0.0f;
		CHECK(vkCreateSampler(dev, &sc, 0, &sampler));
	}
	if (is_texture) {
		/* 4x4 RGBA8 checker (red/green) uploaded through a staging buffer */
		uint32_t texels[16];
		for (int y = 0; y < 4; y++)
			for (int x = 0; x < 4; x++)
				texels[y * 4 + x] = ((x + y) & 1) ? 0xff00ff00u : 0xff0000ffu; /* ABGR: green / red */
		staging = make_buffer(sizeof texels, VK_BUFFER_USAGE_TRANSFER_SRC_BIT);
		memcpy(staging.map, texels, sizeof texels);
		tex = make_image(VK_FORMAT_R8G8B8A8_UNORM, 4, 4,
		    VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT, VK_IMAGE_ASPECT_COLOR_BIT);
	}

	/* Descriptors. */
	VkDescriptorSetLayout dsl = 0;
	VkDescriptorPool dpool = 0;
	VkDescriptorSet dset = 0;
	if (is_ubo || is_texture || is_texlinear) {
		VkDescriptorSetLayoutBinding b = { 0, is_ubo ? VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER
		    : VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, 0 };
		VkDescriptorSetLayoutCreateInfo dlci = { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, 0, 0, 1, &b };
		CHECK(vkCreateDescriptorSetLayout(dev, &dlci, 0, &dsl));
		VkDescriptorPoolSize ps = { b.descriptorType, 1 };
		VkDescriptorPoolCreateInfo dpci = { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO, 0, 0, 1, 1, &ps };
		CHECK(vkCreateDescriptorPool(dev, &dpci, 0, &dpool));
		VkDescriptorSetAllocateInfo dai = { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO, 0, dpool, 1, &dsl };
		CHECK(vkAllocateDescriptorSets(dev, &dai, &dset));
		VkDescriptorBufferInfo dbi = { ubo.b, 0, 16 };
		VkDescriptorImageInfo dii = { sampler, tex.v, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL };
		VkWriteDescriptorSet wds = { VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, 0, dset, 0, 0, 1, b.descriptorType,
		    (is_texture || is_texlinear) ? &dii : 0, is_ubo ? &dbi : 0, 0 };
		vkUpdateDescriptorSets(dev, 1, &wds, 0, 0);
	}

	/* Pipeline. */
	VkPipelineShaderStageCreateInfo stages[2] = {
		{ VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, 0, 0, VK_SHADER_STAGE_VERTEX_BIT,
		  module(dir, shader, "vert"), "main" },
		{ VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, 0, 0, VK_SHADER_STAGE_FRAGMENT_BIT,
		  module(dir, shader, "frag"), "main" },
	};
	VkVertexInputBindingDescription vbd = { 0, 5 * sizeof(float), VK_VERTEX_INPUT_RATE_VERTEX };
	VkVertexInputAttributeDescription vad[2] = { { 0, 0, VK_FORMAT_R32G32_SFLOAT, 0 },
	    { 1, 0, VK_FORMAT_R32G32B32_SFLOAT, 2 * sizeof(float) } };
	VkPipelineVertexInputStateCreateInfo vi = { VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO };
	if (is_vbuf || is_vbufdraw) { vi.vertexBindingDescriptionCount = 1; vi.pVertexBindingDescriptions = &vbd;
		vi.vertexAttributeDescriptionCount = 2; vi.pVertexAttributeDescriptions = vad; }
	VkPipelineInputAssemblyStateCreateInfo ia = { VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
	    0, 0, VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST };
	VkViewport vp = { 0, 0, W, H, 0, 1 };
	VkRect2D sc2 = { { 0, 0 }, { W, H } };
	VkPipelineViewportStateCreateInfo vs = { VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO, 0, 0, 1, &vp, 1, &sc2 };
	VkPipelineRasterizationStateCreateInfo rs = { VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO };
	rs.polygonMode = VK_POLYGON_MODE_FILL; rs.cullMode = VK_CULL_MODE_NONE;
	rs.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE; rs.lineWidth = 1.0f;
	VkPipelineMultisampleStateCreateInfo ms = { VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
	    0, 0, VK_SAMPLE_COUNT_1_BIT };
	VkPipelineDepthStencilStateCreateInfo ds = { VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO };
	ds.depthTestEnable = VK_TRUE; ds.depthWriteEnable = VK_TRUE; ds.depthCompareOp = VK_COMPARE_OP_LESS;
	VkPipelineColorBlendAttachmentState cba = { 0 };
	cba.colorWriteMask = 0xf;
	if (is_blend) {
		cba.blendEnable = VK_TRUE;
		cba.srcColorBlendFactor = VK_BLEND_FACTOR_SRC_ALPHA;
		cba.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
		cba.colorBlendOp = VK_BLEND_OP_ADD;
		cba.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
		cba.dstAlphaBlendFactor = VK_BLEND_FACTOR_ZERO;
		cba.alphaBlendOp = VK_BLEND_OP_ADD;
	}
	VkPipelineColorBlendStateCreateInfo cb = { VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
	    0, 0, 0, 0, 1, &cba };
	VkPipelineLayoutCreateInfo plci = { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, 0, 0, dsl ? 1u : 0u, dsl ? &dsl : 0 };
	VkPipelineLayout layout;
	CHECK(vkCreatePipelineLayout(dev, &plci, 0, &layout));
	VkGraphicsPipelineCreateInfo gp = { VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO };
	gp.stageCount = 2; gp.pStages = stages; gp.pVertexInputState = &vi; gp.pInputAssemblyState = &ia;
	gp.pViewportState = &vs; gp.pRasterizationState = &rs; gp.pMultisampleState = &ms;
	gp.pDepthStencilState = is_depth ? &ds : 0; gp.pColorBlendState = &cb; gp.layout = layout; gp.renderPass = rp;
	VkPipeline pipe;
	CHECK(vkCreateGraphicsPipelines(dev, 0, 1, &gp, 0, &pipe));

	/* Commands. */
	VkCommandPoolCreateInfo cpci = { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, 0, 0, 0 };
	VkCommandPool pool;
	CHECK(vkCreateCommandPool(dev, &cpci, 0, &pool));
	VkCommandBufferAllocateInfo cbai = { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, 0, pool,
	    VK_COMMAND_BUFFER_LEVEL_PRIMARY, 1 };
	VkCommandBuffer cmd;
	CHECK(vkAllocateCommandBuffers(dev, &cbai, &cmd));
	VkCommandBufferBeginInfo bi = { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
	CHECK(vkBeginCommandBuffer(cmd, &bi));
	if (is_texture) {
		barrier(cmd, tex.i, VK_IMAGE_ASPECT_COLOR_BIT, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
		    0, VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
		VkBufferImageCopy up = { 0, 0, 0, { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }, { 0, 0, 0 }, { 4, 4, 1 } };
		vkCmdCopyBufferToImage(cmd, staging.b, tex.i, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &up);
		barrier(cmd, tex.i, VK_IMAGE_ASPECT_COLOR_BIT, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
		    VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT,
		    VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
	}
	if (is_texlinear)
		barrier(cmd, tex.i, VK_IMAGE_ASPECT_COLOR_BIT, VK_IMAGE_LAYOUT_PREINITIALIZED,
		    VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT,
		    VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
	VkClearValue clears[2] = { { .color = { { is_blend ? 0.0f : 0.0f, 0.0f, is_blend ? 1.0f : 0.0f, 1.0f } } },
	    { .depthStencil = { 1.0f, 0 } } };
	VkRenderPassBeginInfo rpbi = { VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO, 0, rp, fb, { { 0, 0 }, { W, H } },
	    is_depth ? 2u : 1u, clears };
	vkCmdBeginRenderPass(cmd, &rpbi, VK_SUBPASS_CONTENTS_INLINE);
	vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe);
	if (dset) vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, layout, 0, 1, &dset, 0, 0);
	if (is_vbuf) {
		VkDeviceSize off = 0;
		vkCmdBindVertexBuffers(cmd, 0, 1, &vbuf.b, &off);
		vkCmdBindIndexBuffer(cmd, ibuf.b, 0, VK_INDEX_TYPE_UINT16);
		vkCmdDrawIndexed(cmd, 6, 1, 0, 0, 0);
	} else if (is_vbufdraw) {
		VkDeviceSize off = 0;
		vkCmdBindVertexBuffers(cmd, 0, 1, &vbuf.b, &off);
		vkCmdDraw(cmd, 6, 1, 0, 0);
	} else if (is_idxonly) {
		vkCmdBindIndexBuffer(cmd, ibuf.b, 0, VK_INDEX_TYPE_UINT16);
		vkCmdDrawIndexed(cmd, 3, 1, 0, 0, 0);
	} else if (is_depth || is_texture || is_texlinear) {
		vkCmdDraw(cmd, 6, 1, 0, 0);
	} else {
		vkCmdDraw(cmd, 3, 1, 0, 0);
	}
	vkCmdEndRenderPass(cmd);
	VkBufferImageCopy copy = { 0, 0, 0, { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }, { 0, 0, 0 }, { W, H, 1 } };
	vkCmdCopyImageToBuffer(cmd, color.i, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, readback.b, 1, &copy);
	CHECK(vkEndCommandBuffer(cmd));
	VkSubmitInfo si = { VK_STRUCTURE_TYPE_SUBMIT_INFO, 0, 0, 0, 0, 1, &cmd };
	CHECK(vkQueueSubmit(queue, 1, &si, 0));
	CHECK(vkQueueWaitIdle(queue));

	/* Reference output: a 16x16 sampled grid (every 4th pixel) and an optional PPM. */
	const uint32_t *px = readback.map;
	printf("scene %s grid16:", scene);
	for (int y = 0; y < H; y += 4)
		for (int x = 0; x < W; x += 4) printf(" %08x", px[y * W + x]);
	printf("\n");
	if (argc > 3) {
		FILE *f = fopen(argv[3], "wb");
		if (f) {
			fprintf(f, "P6\n%d %d\n255\n", W, H);
			for (int i = 0; i < W * H; i++) {
				unsigned char rgb[3] = { px[i] & 0xff, (px[i] >> 8) & 0xff, (px[i] >> 16) & 0xff };
				fwrite(rgb, 1, 3, f);
			}
			fclose(f);
		}
	}
	return 0;
}
