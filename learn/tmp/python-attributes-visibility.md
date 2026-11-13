# `self.xxx = ...` 是对外声明吗？

先纠正一个说法：`self.xxx = ...` 定义的是**实例属性**，不是“类变量”。类变量是写在 `class` 体里的名字，所有实例共享；`self.xxx` 只挂在这一个实例上。

## 对外怎么知道有这个属性

Python 不做字段声明，运行时看实例的 `__dict__`：

```python
policy = Policy(PermissionMode.ASK, allow_commands="echo")
vars(policy)        # 或 policy.__dict__
dir(policy)         # 包含属性 + 方法
```

[`Policy.__init__()`](../../src/minicode/policy.py#L383) 里只有三处 `self.xxx = ...`：

- [`self.mode`](../../src/minicode/policy.py#L389)
- [`self._allow_commands`](../../src/minicode/policy.py#L410)
- [`self._allow_all`](../../src/minicode/policy.py#L411)

所以 `vars(policy)` 就这三个 key。`builtin`、`extra`、`allow_all` 是局部变量，`vars()` 里没有。

设计时想让人知道，可以靠：

- 命名约定：`mode` 是 public，`_allow_commands` / `_allow_all` 是 internal；
- 文档/docstring；
- 类型注解：在类体写 `mode: PermissionMode`，或在 `__init__` 写 `self.mode: PermissionMode = ...`；注解本身不创建值，只给读者和类型检查器看；
- `__slots__`：显式列出允许的属性，同时阻止乱加属性；
- `@dataclass` / `attrs`：适合数据类，`Policy` 这种自定义初始化不一定要用。

## Python 是不是“只开放接口，不推荐访问变量”

不是。Python 没有真正的 private：`_name` 只是“别从外面依赖”的约定，`__name` 会做 name mangling，但也能绕过。类既可以暴露方法，也可以暴露属性；public 属性只要被文档化，就算接口的一部分。

`Policy` 的情况是：

- `mode` 没有下划线，算 public 读属性；
- `_allow_commands`、`_allow_all` 有下划线，表示实现细节，外部不该依赖；
- 外部真正该用的入口是 [`evaluate_command()`](../../src/minicode/policy.py#L413)、[`needs_approval()`](../../src/minicode/policy.py#L448)、[`allows_file_write()`](../../src/minicode/policy.py#L454)。

所以不是“class 对外只开放接口”，而是“作者用命名和文档决定哪些属性算接口”。当前 `Policy` 没有把这些属性写进文档，也没有类级注解，所以它们更接近内部状态；真要让外部稳定使用，应该补注解或改成 property。

一句话：`self.xxx = ...` 是运行时创建实例属性；外部靠 `vars()`/`dir()` 或文档/注解知道它。Python 不禁止访问，只靠命名约定区分 public 和 internal。
