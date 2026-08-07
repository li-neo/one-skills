"""Content Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="内容能力网络",
    description="Routes an explicitly requested book, course, or document method to evidence-linked internal modules. Use for applying distilled content, not for simple summaries or unsupported author claims.",
    role="把内容中的框架、原则、案例、反例和术语组织为可学习、可执行的能力网络。",
    routing_instruction="按用户问题选择框架或原则模块；案例、反例和术语只作为支持节点。",
    governance=("不把摘要冒充能力", "作者局限进入边界", "引用遵守来源和版权范围"),
    output_contract="RIA++ 风格的证据化方法应用结果。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
