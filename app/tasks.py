
"""
Celery Task Registry

L2およびL3 Addonに定義されたTaskを自動的に読み込み、
Celeryへの登録と既存コードとの互換性を維持する。

Taskの実装本体は各レイヤー・Addonのtasks.pyに配置する。
"""

import importlib
from pathlib import Path
from types import ModuleType

from app.celery_app import celery_app


# =========================================================
# Configuration
# =========================================================

ADDONS_DIR = (
    Path(__file__).resolve().parent
    / "layers"
    / "l3_structured"
    / "addons"
)


# =========================================================
# Task Registration
# =========================================================

def register_task_module(
    module: ModuleType,
    registered_tasks: dict,
) -> None:
    """
    Taskモジュールから *_task という名前の属性を取得し、
    登録済みTaskとして管理する。
    """

    for name, task in vars(module).items():

        if name.startswith("_") or not name.endswith("_task"):
            continue

        if not callable(task):
            continue

        if name in registered_tasks:
            raise RuntimeError(
                f"Duplicate Task export detected: {name} "
                f"(module: {module.__name__})"
            )

        registered_tasks[name] = task


# =========================================================
# Addon Discovery
# =========================================================

def discover_addon_task_modules() -> list[str]:
    """
    addonsディレクトリ以下からtasks.pyを再帰的に発見する。

    発見したファイルをPythonのモジュールパスに変換する。
    """

    if not ADDONS_DIR.exists():
        raise RuntimeError(
            f"Addon directory not found: {ADDONS_DIR}"
        )

    module_names = []

    for task_file in sorted(ADDONS_DIR.rglob("tasks.py")):

        relative_path = task_file.relative_to(
            Path(__file__).resolve().parent
        )

        module_name = ".".join(
            relative_path.with_suffix("").parts
        )

        module_names.append(
            f"app.{module_name}"
        )

    return module_names


# =========================================================
# Registry Initialization
# =========================================================

def initialize_task_registry() -> list[str]:
    """
    L2およびL3 AddonのTaskを読み込み、
    app.tasksから利用できるように公開する。

    Returns:
        list[str]: 公開したTask名
    """

    registered_tasks = {}

    # -----------------------------------------------------
    # L2 Tasks
    # -----------------------------------------------------

    l2_module = importlib.import_module(
        "app.layers.l2_extracted.tasks"
    )

    register_task_module(
        l2_module,
        registered_tasks,
    )

    # -----------------------------------------------------
    # L3 Addon Tasks
    # -----------------------------------------------------

    addon_modules = discover_addon_task_modules()

    print(
        f"[Celery Registry] Discovered "
        f"{len(addon_modules)} Addon Task module(s)."
    )

    for module_name in addon_modules:

        print(
            f"[Celery Registry] Loading: {module_name}"
        )

        module = importlib.import_module(module_name)

        register_task_module(
            module,
            registered_tasks,
        )

    # -----------------------------------------------------
    # Public Exports
    # -----------------------------------------------------

    globals().update(registered_tasks)

    exported_names = [
        "celery_app",
        *registered_tasks.keys(),
    ]

    globals()["__all__"] = exported_names

    print(
        "[Celery Registry] Initialization completed. "
        f"Exported tasks: {len(registered_tasks)}"
    )

    return exported_names


# =========================================================
# Initialization
# =========================================================

initialize_task_registry()

