"""Hybrid Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="复合对象能力路由器",
    description="Routes an explicitly requested hybrid object across person, knowledge, method, workflow, and tool modules while preserving each source's permissions. Use for cross-module outcomes.",
    role="拆分子对象、隔离权限、传递结构化状态，并验证整体业务闭环。",
    routing_instruction="先选择子 Profile，再按 depends_on 和 hands_off_to 编排模块。",
    governance=("不同来源权限不得互相扩大", "模块冲突必须升级", "每个子结果和整体结果都要验证"),
    output_contract="包含路由、子能力结果、交接状态和整体完成条件的复合交付。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
