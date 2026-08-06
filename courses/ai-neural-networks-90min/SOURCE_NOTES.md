# 来源、证据与版权说明

## 来源分工

本课程没有让单一网页同时承担作品身份、逐字文本和时间轴三种证据。

| 来源 | 证据角色 | 使用方式 |
|---|---|---|
| [抖音精选作品页](https://jingxuan.douyin.com/m/video/7427381362337778980) | 作品身份 | 确认用户指定的作者与作品 |
| [B 站作者同版视频](https://www.bilibili.com/video/BV1atCRYsE7x) | 主时间线、画面 | 固定 88:58 版本的顺序、章节边界和截图 |
| [LilysAI 字幕镜像](https://lilys.ai/zh/notes/physical-ai-20251225/deep-dive-ai-neural-networks-explained) | 文本交叉核对 | 核对前半段概念、人物、术语和论证顺序 |

## 时间线校准

- B 站 API 元数据：`bvid=BV1atCRYsE7x`、`aid=113332711333508`、`cid=26360022345`、时长 `5338` 秒。
- B 站没有公开字幕列表，也没有视频章节列表。
- 课程先对作者同版音轨做本地自动语音识别，只用于查找语义转场；再以视频画面复核并提取截图。
- LilysAI 页面在引用外部采访及素材后出现时间戳跳变，而且没有覆盖 B 站 88:58 版中完整的 GPT 和扩散模型段落。因此，它不用于正式时间线。
- 课程正文是结构化转述，不是逐字稿。自动识别中的错字、误听和断句没有进入正文。

## 截图清单

所有截图均来自作者同版视频，仅用于说明对应知识点。

| 文件 | 视频时间 | 用途 |
|---|---:|---|
| `01-dartmouth-conference.jpg` | 00:53 | AI 起点 |
| `02-intelligence-as-function.jpg` | 04:11 | 输入输出函数 |
| `03-symbolism.jpg` | 05:59 | 符号主义 |
| `04-machine-learning.jpg` | 08:58 | 机器学习 |
| `05-perceptron.jpg` | 14:52 | 感知机 |
| `06-xor-limit.jpg` | 21:44 | XOR 局限 |
| `07-multilayer-perceptron.jpg` | 25:56 | 多层感知机 |
| `08-loss-function.jpg` | 31:24 | 损失函数 |
| `09-gradient-descent.jpg` | 39:34 | 梯度下降 |
| `10-backpropagation.jpg` | 41:42 | 反向传播 |
| `11-generalization.jpg` | 47:06 | 泛化 |
| `12-next-token-generation.jpg` | 53:38 | 自回归生成 |
| `13-next-token-prediction.jpg` | 62:04 | 下一 Token 预测 |
| `14-diffusion-model.jpg` | 70:54 | 扩散模型 |
| `15-neural-network-denoising.jpg` | 82:27 | 神经网络去噪 |
| `16-ai-and-work.jpg` | 85:38 | AI 与工作 |

## 版权边界

- 原视频、Manim 动画、引用片段和截图版权归漫士沉思录及相应素材权利人所有。
- 原作者在视频简介中说明使用了 3Blue1Brown、Artem Kirsanov 等素材；本课程不改变其归属。
- 本课程是学习研究用途的转换性文字笔记，不能替代原视频，也不能冒充原作者作品。
- 对外发布或商业使用前，应重新获得原视频及相应画面素材的许可。
