# SceneFlow 免责声明 / Disclaimer

## 中文版本 (Chinese Version)

在使用、部署、复制、修改或分发 SceneFlow 项目（以下简称“本项目”）之前，请仔细阅读本免责声明。使用本项目即表示你已充分理解并无保留地接受以下全部条款：

### 1. 按“原样”提供与无保证
本项目遵循 **GNU Affero General Public License v3.0 (AGPL-3.0)** 协议开源，并按“原样”（AS IS）和“现有”（AS AVAILABLE）状态提供。项目作者、维护者及贡献者不对软件的功能完整性、稳定性、安全性、准确性、特定用途适用性或不侵权性作任何明示或默示的保证。使用者须自行承担测试、数据备份及部署运行的所有风险。

### 2. AI 生成内容与输出风险
本项目作为 AI 辅助创作工具，调用的底层大语言模型（LLM）、图像生成模型、语音合成（TTS）及视频生成等模型具备不确定性：
- 模型的输出可能包含事实性错误、逻辑幻觉、偏见、有害信息或侵权风险，并不代表本项目作者或贡献者的观点或立场；
- 在公开发布、商业运营、传播或依据生成内容采取行动之前，使用者必须进行独立的人工审核与事实核验；
- 本项目及其生成内容均不构成任何法律、金融、医疗、版权合规或其他专业领域的建议或承诺。

### 3. 使用者合规与法律责任
- 使用者应确保其输入的提示词（Prompts）、剧本、上传的参考图像、声音素材、角色设定及其他数据均具备合法来源与必要授权；
- 使用者须严格遵守适用的版权、商标、肖像权、隐私权、数据保护法、网络安全法、人工智能管理法规及社会公序良俗；
- **严禁**利用本项目从事任何违法犯罪活动、制作与传播虚假违规信息、实施未经授权的人脸/声音伪造（Deepfake）、侵犯他人合法权益或进行网络欺诈。因使用者上述行为引发的任何法律诉讼、争议、行政处罚或损害赔偿，概由使用者自行独立承担。

### 4. 第三方服务与 API 约束
本项目集成了多家第三方模型与 API 服务（包括但不限于 OpenAI、Gemini、ElevenLabs、阿里云、火山引擎等）。第三方服务受其各自的服务条款、隐私协议、使用限制和计费策略约束。对于第三方服务的接口变更、网络中断、服务终止、账号封禁、费用调整或数据处理问题，本项目作者不承担任何责任。

### 5. 凭证与数据安全
使用者和部署者负责妥善保管自身的 API 密钥、数据库、管理密码、JWT 签名密钥及服务器访问权限。请勿将包含真实凭据的配置文件、运行时数据库（如 `sceneflow.db`）或生成的私有媒体文件提交至公开仓库。项目作者不对因安全配置不当或外部攻击导致的密钥泄露、数据丢失或未授权访问承担责任。

### 6. 责任限制
在适用法律允许的最大范围内，项目作者、维护者及贡献者在任何情况下均不对因使用、无法使用、修改或分发本项目而产生的任何直接、间接、附带、特殊、惩罚性或后果性损失（包括但不限于利润损失、业务中断、数据丢失、API 调用费用损失、第三方索赔等）承担责任。

### 7. AGPL-3.0 协议与网络部署声明
本项目遵循 GNU AGPL-3.0 开源协议。任何通过计算机网络向用户提供远程交互服务（如 SaaS 模式）或二次分发修改版的使用者，均须遵守 AGPL-3.0 协议关于公开对应修改后源代码的义务。进行网络部署或商业运营并不免除本免责声明的约束，项目原作者与贡献者不对任何下游最终用户承担任何技术支持、质量保证或连带赔偿责任。

---

## English Version

Please read this Disclaimer carefully before using, deploying, copying, modifying, or distributing the SceneFlow project (the "Software"). By using this Software, you acknowledge and agree to all of the following terms:

### 1. "As-Is" Software and No Warranty
This Software is open-sourced under the **GNU Affero General Public License v3.0 (AGPL-3.0)** and provided on an "AS IS" and "AS AVAILABLE" basis. The authors, maintainers, and contributors make no representations or warranties of any kind, express or implied, regarding functionality, stability, security, accuracy, continuous availability, fitness for a particular purpose, or non-infringement. You assume all risks associated with testing, backups, and operation.

### 2. AI-Generated Output and Inherent Risks
The Software leverages artificial intelligence models (including LLMs, image generation, text-to-speech, and video generation) whose outputs are inherently non-deterministic:
- Model output may contain factual inaccuracies, hallucinations, bias, inappropriate content, or potential infringement, and does not reflect the views or positions of the project authors;
- Users must independently review and verify all generated content before publishing, broadcasting, commercializing, or relying on it;
- Neither the Software nor its generated output constitutes medical, legal, financial, copyright compliance, or other professional advice.

### 3. Legal Compliance and User Responsibility
- Users are solely responsible for ensuring lawful access to, ownership of, and necessary permissions for all prompts, scripts, reference portraits, audio samples, character designs, and other content processed by the Software;
- Users must strictly comply with applicable copyright, trademark, publicity, privacy, data protection, artificial intelligence, and cybersecurity laws;
- **Using the Software for any unlawful, infringing, fraudulent, defamatory, or harmful activities—including unauthorized impersonation (Deepfake) or creating illegal content—is strictly prohibited.** Users bear sole legal responsibility for any claims, damages, penalties, or liabilities arising from their conduct.

### 4. Third-Party Services and APIs
The Software integrates with third-party model providers, APIs, and cloud services (such as OpenAI, Gemini, ElevenLabs, and others). These services are governed exclusively by their respective terms of service, privacy policies, pricing, and regional limitations. The authors are not responsible for API modifications, service interruptions, account terminations, rate limits, quota exhaustion, or third-party fees.

### 5. Credentials and Data Security
Users and operators are responsible for protecting their own API keys, passwords, database connections, JWT secrets, and server infrastructure. Avoid committing sensitive secrets, runtime databases (such as `sceneflow.db`), or generated media assets to public repositories. The authors are not liable for security breaches, credential exposures, data loss, or unauthorized access resulting from improper configuration.

### 6. Limitation of Liability
To the maximum extent permitted by applicable law, in no event shall the authors, maintainers, or contributors be liable for any direct, indirect, incidental, special, exemplary, punitive, or consequential damages (including loss of profits, business interruption, data loss, API consumption expenses, or third-party claims) arising from the use of, or inability to use, this Software.

### 7. AGPL-3.0 Compliance and Network Deployment
This Software is distributed under the GNU AGPL-3.0 license. Anyone who modifies the Software and provides remote network access (such as SaaS hosting) must comply with the AGPL-3.0 obligation to offer the Corresponding Source to all interacting users. Deploying or operating the Software commercially does not waive or alter this Disclaimer, and the original authors owe no support, warranty, or indemnification obligations to downstream users or customers.


1. 注册时邮箱改为非必填
2. 配置视频模型时，千问还需要新增wan2.7
3. 豆包的视频模型，选了过后自动填充的支持图片支持参考视频支持参考音频好像不是很对


ai生剧 剧集编辑页面的，有些需要修改的
1. 删除说话角色，这里对应角色的台词，在用户点击生成视频分镜的时候，会自动识别有台词的镜头，然后把台词和角色塞到空镜头里面，就不用再添加说话角色这个组件了
2. 画面提示词和视频提示词默认的 @参考素材没有展示在下面并且支持删除，比如默认的参考素材传给大模型的时候最终提示词会变成变成图片一并且传入图片的顺序默认参考素材也会是第一个，并且提示词也没有看出来使用了默认的参考素材， 后续手动@的素材 @后输入框会有两个@符号 并且下面如果点击删除了参考素材，输入框里面的也不会对应消失掉
3. 视频最终提示词预览的时候我发现没有把@的素材转化为 对应视频模型能识别的映射关系 比如我如果用的豆包的模型那么我“@韩立青年”这个素材的时候，然后预览的最终提示词应该是 <图片N>，如果细节一点的话那么就是<图片N> 韩立青年，这里需要参考对应模型的文档做转换
https://docs.volcengine.com/docs/82379/2607689?lang=zh Doubao Seedance 2.5 提示词指南
https://docs.volcengine.com/docs/82379/2222480?lang=zh Doubao Seedance 2.0 系列提示词指南
https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference?spm=a2c4g.11186623.help-menu-2400256.d_2_3_1_0.7f404f61F1RQJj&scm=20140722.H_3049634._.OR_help-T_cn~zh-V_1 万相3.0-视频生成API参考
https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference?spm=a2c4g.11186623.help-menu-2400256.d_2_3_1_3.37ce76a6whgM6O&scm=20140722.H_3001146._.OR_help-T_cn~zh-V_1 万相2.7-参考生视频API参考
图片的预览功能也需要加上 统一就是图片1 或者图1 这种映射格式 并且支持删除默认的
4.  @参考素材支持键盘上下切换以及回车选中
