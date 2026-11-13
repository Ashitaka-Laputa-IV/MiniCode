# `Policy` 的 `self` 里有什么

`self` 就是 `Policy` 的实例本身，不需要在类体里“定义”。`Policy(...)` 创建实例时会调用 [`__init__()`](../../src/minicode/policy.py#L383)，Python 自动把新实例作为第一个参数传进去，这个参数名就是 `self`。

## `self` 里实际有什么

`__init__` 里给 `self` 赋值的属性只有三个：

- [`self.mode`](../../src/minicode/policy.py#L389)：`PermissionMode` 枚举。
- [`self._allow_commands`](../../src/minicode/policy.py#L410)：去重后的 safe 命令前缀元组。
- [`self._allow_all`](../../src/minicode/policy.py#L411)：`allow_commands` 里是否出现过 `all`。

其余变量是局部变量，不属于 `self`：

- `builtin`、`extra`、`allow_all`、`items`、`item`、`lowered` 都只在 `__init__` 调用期间存在，函数返回后就没了。
- 只有写成 `self.xxx = ...` 的赋值才会挂到实例上。

可以用 `vars(policy)` 看实例的 `__dict__`：

```python
from minicode.policy import PermissionMode, Policy

policy = Policy(PermissionMode.ASK, allow_commands="echo")
vars(policy)
# {
#   "mode": <PermissionMode.ASK: "ask">,
#   "_allow_commands": ("ls", "dir", ..., "echo"),
#   "_allow_all": False,
# }
```

`Policy` 没有定义 `__slots__`，所以实例默认有 `__dict__`，属性是动态挂上去的；这就是为什么类体里看不到 `mode = ...` 这样的声明。

## 方法怎么用到这些属性

后面的方法都通过 `self` 读：

- [`evaluate_command()`](../../src/minicode/policy.py#L413) 读 `self.mode` 和 `self._allow_all`。
- [`needs_approval()`](../../src/minicode/policy.py#L448) 读 `self.mode`。
- [`allows_file_write()`](../../src/minicode/policy.py#L454) 读 `self.mode`。
- [`_is_safe()`](../../src/minicode/policy.py#L457) 读 `self._allow_commands`。

如果某个属性还没在 `__init__` 里赋值就被访问，会直接 `AttributeError`。Python 不要求提前声明字段；第一次 `self.xxx = ...` 就是定义。

一句话：`self` 是实例，不是类体里的一个变量；`__init__` 里 `self.xxx = ...` 的那些 `xxx` 才是它的属性。
