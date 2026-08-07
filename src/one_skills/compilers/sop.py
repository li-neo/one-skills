"""SOP Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="可恢复 SOP 工作流",
    description="Runs an authorized SOP as an evidence-linked state workflow. Use for repeatable operational execution with roles, handoffs, verification, exceptions, rollback, and read-back.",
    role="按状态执行流程并记录责任人、输入、输出和读回，不跳过破坏性动作确认。",
    routing_instruction="根据当前状态和异常类型选择步骤、交接、验证或回滚模块。",
    governance=("权限最小化", "破坏性动作先确认", "异常必须回滚或升级", "完成后跨系统读回"),
    output_contract="可审计的状态迁移、操作结果、读回和闭环记录。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
