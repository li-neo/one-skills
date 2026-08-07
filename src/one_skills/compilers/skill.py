"""Existing-Skill Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="Whole-folder Skill 修复器",
    description="Diagnoses and repairs an existing Agent Skill folder. Use when trigger, workflow, scripts, references, tests, or regressions need evidence-linked changes without changing core purpose.",
    role="以整个 Skill 目录为修改单位，冻结核心用途、基线和失败测试。",
    routing_instruction="按缺陷位置选择 trigger、workflow、script、reference 或 test 模块。",
    governance=("不得静默改变核心用途", "不得删除失败测试提分", "任何修改必须有 before/after"),
    output_contract="可归因的 whole-folder patch、回归结果和 keep/revert 建议。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
