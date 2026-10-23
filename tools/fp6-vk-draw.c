/* Offscreen Vulkan triangle used only to make Mesa/Turnip emit an A810 draw
 * command stream on a host (no GPU, no window): run it under the freedreno noop
 * drm-shim with FD_RD_DUMP=enable,full and decode the .rd capture.
 *
 *   glslangValidator -V draw.vert -o vert.spv
 *   glslangValidator -V draw.frag -o frag.spv
 *   cc -O1 -o fp6-vk-draw fp6-vk-draw.c -lvulkan
 *   LD_PRELOAD=libfreedreno_noop_drm_shim.so FD_GPU_ID=810 \
 *     VK_DRIVER_FILES=freedreno_icd.x86_64.json \
 *     FD_RD_DUMP=enable,full FD_RD_DUMP_PATH=DIR ./fp6-vk-draw vert.spv frag.spv
 *
 * Nothing is read back meaningfully under the shim; only the submitted command
 * streams and buffers matter.
 *
 * Optional screen mode, to make a stream that draws straight into a scanout
 * framebuffer of the given geometry:
 *   fp6-vk-draw vert.spv frag.spv SIZE FBW FBH X Y
 * renders a SIZE x SIZE B8G8R8A8 image and copies it into a FBW x FBH x 4 byte
 * buffer at pixel (X, Y) with bufferRowLength = FBW (the scanout pitch). */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define CHECK(x) do { VkResult r_ = (x); if (r_ != VK_SUCCESS) { \
	fprintf(stderr, "%s failed: %d (line %d)\n", #x, r_, __LINE__); exit(1); } } while (0)
static unsigned W = 64, H = 64;
static unsigned FBW, FBH, FBX, FBY; /* screen mode when FBW != 0 */

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

static uint32_t memtype(VkPhysicalDevice pd, uint32_t bits, VkMemoryPropertyFlags want)
{
	VkPhysicalDeviceMemoryProperties mp;
	vkGetPhysicalDeviceMemoryProperties(pd, &mp);
	for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
		if ((bits & (1u << i)) && (mp.memoryTypes[i].propertyFlags & want) == want) return i;
	fprintf(stderr, "no memory type\n");
	exit(1);
}

static VkShaderModule module(VkDevice dev, const char *path)
{
	size_t size;
	uint32_t *code = load(path, &size);
	VkShaderModuleCreateInfo ci = { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, 0, 0, size, code };
	VkShaderModule m;
	CHECK(vkCreateShaderModule(dev, &ci, 0, &m));
	return m;
}

int main(int argc, char **argv)
{
	if (argc != 3 && argc != 8) {
		fprintf(stderr, "usage: %s vert.spv frag.spv [SIZE FBW FBH X Y]\n", argv[0]);
		return 2;
	}
	if (argc == 8) {
		W = H = (unsigned)atoi(argv[3]);
		FBW = (unsigned)atoi(argv[4]); FBH = (unsigned)atoi(argv[5]);
		FBX = (unsigned)atoi(argv[6]); FBY = (unsigned)atoi(argv[7]);
		if (!W || !FBW || !FBH || FBX + W > FBW || FBY + H > FBH) {
			fprintf(stderr, "bad geometry\n");
			return 2;
		}
	}
	VkApplicationInfo app = { VK_STRUCTURE_TYPE_APPLICATION_INFO, 0, "fp6-vk-draw", 1, "none", 1,
	    VK_API_VERSION_1_1 };
	VkInstanceCreateInfo ici = { VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, 0, 0, &app };
	VkInstance inst;
	CHECK(vkCreateInstance(&ici, 0, &inst));
	uint32_t n = 1;
	VkPhysicalDevice pd;
	VkResult e = vkEnumeratePhysicalDevices(inst, &n, &pd);
	if ((e != VK_SUCCESS && e != VK_INCOMPLETE) || n < 1) { fprintf(stderr, "no device\n"); return 1; }
	VkPhysicalDeviceProperties props;
	vkGetPhysicalDeviceProperties(pd, &props);
	printf("device: %s\n", props.deviceName);
	float prio = 1.0f;
	VkDeviceQueueCreateInfo qci = { VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, 0, 0, 0, 1, &prio };
	VkDeviceCreateInfo dci = { VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, 0, 0, 1, &qci };
	VkDevice dev;
	CHECK(vkCreateDevice(pd, &dci, 0, &dev));
	VkQueue queue;
	vkGetDeviceQueue(dev, 0, 0, &queue);

	VkImageCreateInfo img = { VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO };
	img.imageType = VK_IMAGE_TYPE_2D;
	img.format = FBW ? VK_FORMAT_B8G8R8A8_UNORM : VK_FORMAT_R8G8B8A8_UNORM;
	img.extent = (VkExtent3D){ W, H, 1 }; img.mipLevels = 1; img.arrayLayers = 1;
	img.samples = VK_SAMPLE_COUNT_1_BIT; img.tiling = VK_IMAGE_TILING_OPTIMAL;
	img.usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
	img.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
	VkImage image;
	CHECK(vkCreateImage(dev, &img, 0, &image));
	VkMemoryRequirements mr;
	vkGetImageMemoryRequirements(dev, image, &mr);
	VkMemoryAllocateInfo mai = { VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, 0, mr.size,
	    memtype(pd, mr.memoryTypeBits, 0) };
	VkDeviceMemory imem;
	CHECK(vkAllocateMemory(dev, &mai, 0, &imem));
	CHECK(vkBindImageMemory(dev, image, imem, 0));
	VkImageViewCreateInfo vci = { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO };
	vci.image = image; vci.viewType = VK_IMAGE_VIEW_TYPE_2D; vci.format = img.format;
	vci.subresourceRange = (VkImageSubresourceRange){ VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
	VkImageView view;
	CHECK(vkCreateImageView(dev, &vci, 0, &view));

	VkBufferCreateInfo bci = { VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, 0, 0,
	    FBW ? (VkDeviceSize)FBW * FBH * 4 : (VkDeviceSize)W * H * 4,
	    VK_BUFFER_USAGE_TRANSFER_DST_BIT };
	VkBuffer buf;
	CHECK(vkCreateBuffer(dev, &bci, 0, &buf));
	vkGetBufferMemoryRequirements(dev, buf, &mr);
	mai.allocationSize = mr.size;
	mai.memoryTypeIndex = memtype(pd, mr.memoryTypeBits,
	    VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
	VkDeviceMemory bmem;
	CHECK(vkAllocateMemory(dev, &mai, 0, &bmem));
	CHECK(vkBindBufferMemory(dev, buf, bmem, 0));

	VkAttachmentDescription att = { 0, img.format, VK_SAMPLE_COUNT_1_BIT,
	    VK_ATTACHMENT_LOAD_OP_CLEAR, VK_ATTACHMENT_STORE_OP_STORE,
	    VK_ATTACHMENT_LOAD_OP_DONT_CARE, VK_ATTACHMENT_STORE_OP_DONT_CARE,
	    VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL };
	VkAttachmentReference ref = { 0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL };
	VkSubpassDescription sub = { 0, VK_PIPELINE_BIND_POINT_GRAPHICS, 0, 0, 1, &ref };
	VkRenderPassCreateInfo rpci = { VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO, 0, 0, 1, &att, 1, &sub };
	VkRenderPass rp;
	CHECK(vkCreateRenderPass(dev, &rpci, 0, &rp));
	VkFramebufferCreateInfo fci = { VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO, 0, 0, rp, 1, &view, W, H, 1 };
	VkFramebuffer fb;
	CHECK(vkCreateFramebuffer(dev, &fci, 0, &fb));

	VkPipelineShaderStageCreateInfo stages[2] = {
		{ VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, 0, 0, VK_SHADER_STAGE_VERTEX_BIT,
		  module(dev, argv[1]), "main" },
		{ VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, 0, 0, VK_SHADER_STAGE_FRAGMENT_BIT,
		  module(dev, argv[2]), "main" },
	};
	VkPipelineVertexInputStateCreateInfo vi = { VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO };
	VkPipelineInputAssemblyStateCreateInfo ia = { VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
	    0, 0, VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST };
	VkViewport vp = { 0, 0, W, H, 0, 1 };
	VkRect2D sc = { { 0, 0 }, { W, H } };
	VkPipelineViewportStateCreateInfo vs = { VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
	    0, 0, 1, &vp, 1, &sc };
	VkPipelineRasterizationStateCreateInfo rs = { VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO };
	rs.polygonMode = VK_POLYGON_MODE_FILL; rs.cullMode = VK_CULL_MODE_NONE;
	rs.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE; rs.lineWidth = 1.0f;
	VkPipelineMultisampleStateCreateInfo ms = { VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
	    0, 0, VK_SAMPLE_COUNT_1_BIT };
	VkPipelineColorBlendAttachmentState cba = { 0 };
	cba.colorWriteMask = 0xf;
	VkPipelineColorBlendStateCreateInfo cb = { VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
	    0, 0, 0, 0, 1, &cba };
	VkPipelineLayoutCreateInfo plci = { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO };
	VkPipelineLayout layout;
	CHECK(vkCreatePipelineLayout(dev, &plci, 0, &layout));
	VkGraphicsPipelineCreateInfo gpci = { VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO };
	gpci.stageCount = 2; gpci.pStages = stages; gpci.pVertexInputState = &vi;
	gpci.pInputAssemblyState = &ia; gpci.pViewportState = &vs; gpci.pRasterizationState = &rs;
	gpci.pMultisampleState = &ms; gpci.pColorBlendState = &cb; gpci.layout = layout;
	gpci.renderPass = rp;
	VkPipeline pipe;
	CHECK(vkCreateGraphicsPipelines(dev, 0, 1, &gpci, 0, &pipe));

	VkCommandPoolCreateInfo cpci = { VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, 0, 0, 0 };
	VkCommandPool pool;
	CHECK(vkCreateCommandPool(dev, &cpci, 0, &pool));
	VkCommandBufferAllocateInfo cbai = { VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, 0, pool,
	    VK_COMMAND_BUFFER_LEVEL_PRIMARY, 1 };
	VkCommandBuffer cmd;
	CHECK(vkAllocateCommandBuffers(dev, &cbai, &cmd));
	VkCommandBufferBeginInfo bi = { VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO };
	CHECK(vkBeginCommandBuffer(cmd, &bi));
	VkClearValue clear = { .color = { { 0.0f, 0.0f, FBW ? 0.3f : 0.0f, 1.0f } } };
	VkRenderPassBeginInfo rpbi = { VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO, 0, rp, fb,
	    { { 0, 0 }, { W, H } }, 1, &clear };
	vkCmdBeginRenderPass(cmd, &rpbi, VK_SUBPASS_CONTENTS_INLINE);
	vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, pipe);
	vkCmdDraw(cmd, 3, 1, 0, 0);
	vkCmdEndRenderPass(cmd);
	VkBufferImageCopy copy = { FBW ? ((VkDeviceSize)FBY * FBW + FBX) * 4 : 0, FBW, 0,
	    { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }, { 0, 0, 0 }, { W, H, 1 } };
	vkCmdCopyImageToBuffer(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, buf, 1, &copy);
	CHECK(vkEndCommandBuffer(cmd));
	VkSubmitInfo si = { VK_STRUCTURE_TYPE_SUBMIT_INFO, 0, 0, 0, 0, 1, &cmd };
	CHECK(vkQueueSubmit(queue, 1, &si, 0));
	CHECK(vkQueueWaitIdle(queue));
	printf("submitted\n");
	return 0;
}
