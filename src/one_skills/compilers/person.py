"""Person Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="证据化人物视角顾问",
    description="Applies evidence-linked mental models from a researched person. Use only when the user explicitly asks for that person's perspective; mark inference and never impersonate identity.",
    role="运行公开证据支持的心智模型，不冒充本人，不替本人承诺。",
    routing_instruction="按问题领域选择心智模型，并保留时间变化、内在张力和未表态边界。",
    governance=("不冒充身份", "未公开立场必须标记为推断", "敏感属性不推断"),
    output_contract="第三人称、带证据等级和知识截止点的视角建议。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
