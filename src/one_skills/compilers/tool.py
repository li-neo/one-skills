"""Tool Profile compiler."""

from pathlib import Path

from . import ProfileCompilerConfig, compile_profile_network, load_confirmed_candidates

CONFIG = ProfileCompilerConfig(
    title="工具操作路由器",
    description="Routes an explicitly requested tool operation through validated contracts, authentication, side-effect, error, and read-back modules. Use for controlled tool execution, not credential disclosure.",
    role="把工具文档编译为最小权限、Schema 校验、受控调用和读回验证。",
    routing_instruction="按操作类型选择 contract 模块；写操作必须同时加载副作用和 read-back 模块。",
    governance=("不得输出密钥", "校验版本和 Schema", "外部写入需授权", "执行后只读验证"),
    output_contract="工具调用、错误处理、读回证据和审计信息。",
)


def compile_pack(pack: Path):
    return compile_profile_network(pack, load_confirmed_candidates(pack), CONFIG)
