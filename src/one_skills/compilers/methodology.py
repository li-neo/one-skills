"""Methodology Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="证据化方法工具",
    description="Routes an explicitly requested methodology to evidence-linked internal modules. Use when the user wants to diagnose and act with that method; stop when assumptions, evidence, law, or safety gates fail.",
    role="运行方法结构，不模拟作者身份，不把历史或理论断言冒充现实效果。",
    routing_instruction="先检查成立假设，再按问题类型选择一个主模块和最多一个辅助模块。",
    governance=("成立假设不满足时停止", "保留反证和改判条件", "行动必须守法、可逆并可复核"),
    output_contract="包含问题、假设、机制、步骤、分支、完成、停止和回滚的执行结果。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
