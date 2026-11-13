# Python 基础：类、实例、`self`、属性和可见性

这篇只讲读懂 `Policy` 需要的 Python 基础：类和实例、`__init__`、`self`、实例属性、类属性、`classmethod`、命名约定，以及 `setdefault`。

## 1. 类不是实例

`class` 定义的是“类对象”，调用它才会创建实例：

```python
class Counter:
    kind = "counter"          # 类属性，所有实例共享

    def __init__(self, start=0):
        self.value = start    # 实例属性，每个实例一份

c = Counter(10)
```

- `Counter.kind` 和 `c.kind` 都能读到 `"counter"`。
- `c.value` 只存在于 `c` 这个实例上；另一个 `Counter()` 有自己的 `value`。
- 给 `c.kind = "x"` 会在 `c` 上创建一个实例属性，遮住类属性；`Counter.kind` 仍然是 `"counter"`。

[`Policy`](../../src/minicode/policy.py#L380) 没有类属性；`mode`、`_allow_commands`、`_allow_all` 都是实例属性。

## 2. `__init__` 和 `self`

`Policy(...)` 创建实例后，Python 自动调用 [`__init__()`](../../src/minicode/policy.py#L383)，并把新实例作为第一个参数传进去。这个参数约定叫 `self`。

```python
def __init__(self, mode=PermissionMode.ASK):
    self.mode = PermissionMode.parse(mode)
```

- `self` 不是关键字，也不是“类里的变量”；它只是实例参数的惯例名字。
- 写 `self.mode = ...` 就是在当前实例上创建 `mode` 属性。
- 不写 `self` 的变量是局部变量，函数结束就没了。`Policy.__init__` 里的 `builtin`、`extra`、`allow_all` 都是局部变量。

方法也是同理：

```python
def evaluate_command(self, command):
    ...
```

调用 `policy.evaluate_command("ls")` 时，Python 自动把 `policy` 传给 `self`。等价于 `Policy.evaluate_command(policy, "ls")`。

## 3. 属性不需要提前声明

Python 不要求写“字段声明”。第一次 `self.xxx = ...` 就是定义；之后所有方法都能通过 `self.xxx` 读。没赋值就访问会 `AttributeError`。

运行时能看到实例上有什么：

```python
policy = Policy(PermissionMode.ASK)
vars(policy)      # 或 policy.__dict__
dir(policy)       # 属性 + 方法 + 类属性
```

[`Policy`](../../src/minicode/policy.py#L380) 的实例上只有三个属性：

- [`self.mode`](../../src/minicode/policy.py#L389)
- [`self._allow_commands`](../../src/minicode/policy.py#L410)
- [`self._allow_all`](../../src/minicode/policy.py#L411)

`vars(policy)` 不会列出 `evaluate_command` 这样的方法，因为方法在类上，不在实例的 `__dict__` 里。

## 4. 类属性、实例属性和方法

- **类属性**：写在 `class` 体里，所有实例共享；例如 `kind = "counter"`。
- **实例属性**：通过 `self.x = ...` 创建，每个实例一份；例如 `self.mode`。
- **方法**：也是类上的属性，只是它是函数；通过实例调用时自动绑定 `self`。

属性查找顺序是：先找实例 `__dict__`，找不到再找类。所以实例属性可以遮住同名类属性。

一个常见坑是把可变对象写成类属性：

```python
class Bad:
    items = []          # 所有实例共享同一个 list

    def add(self, x):
        self.items.append(x)   # 改的是类属性，不是每个实例一份
```

`Policy` 没有这个坑，因为 `_allow_commands`、`_allow_all` 都在 `__init__` 里赋给 `self`。

## 5. `classmethod`、`staticmethod`、`property`

`@classmethod` 的第一个参数是**类**，约定叫 `cls`：

```python
class PermissionMode(str, Enum):
    @classmethod
    def parse(cls, value):
        ...
        return cls(value)
```

- `PermissionMode.parse("ask")` 里 `cls` 是 `PermissionMode`。
- 子类调用时 `cls` 是子类，所以 `cls(value)` 会构造子类成员。
- [`PermissionMode.parse()`](../../src/minicode/policy.py#L18) 还用了 `isinstance(value, cls)` 判断“已经是这个枚举实例”，是就直接返回。

`@staticmethod` 不需要 `self`/`cls`，只是挂在类命名空间里的普通函数。`@property` 让方法可以像属性一样访问，常用于只读属性或计算属性。

`__slots__` 是另一种声明方式：

```python
class Point:
    __slots__ = ("x", "y")
```

它显式限制实例只能有 `x`/`y`，没有 `__dict__`，也更省内存。`Policy` 没用 `__slots__`，所以属性是动态的。

## 6. Python 没有真正的 private

Python 靠约定，不靠访问控制：

- `_name`：内部实现，外部最好别依赖。
- `__name`：会被 name mangling 成 `_Class__name`，但不是安全机制，仍可绕过。
- 没有下划线的属性：可以视为 public，只要文档/类型注解把它当接口。

`Policy` 里：

- [`mode`](../../src/minicode/policy.py#L389) 没有下划线，算 public 读属性；
- [`_allow_commands`](../../src/minicode/policy.py#L410)、[`_allow_all`](../../src/minicode/policy.py#L411) 有下划线，是实现细节；
- 外部真正该用的入口是 [`evaluate_command()`](../../src/minicode/policy.py#L413)、[`needs_approval()`](../../src/minicode/policy.py#L448)、[`allows_file_write()`](../../src/minicode/policy.py#L454)。

所以不是“类只开放接口”，而是“作者用命名和文档决定哪些属性算接口”。Python 不禁止你访问 `_allow_commands`，只是不保证它以后不变。

想让属性对外更明确，可以加类型注解：

```python
class Policy:
    mode: PermissionMode
    _allow_commands: tuple[str, ...]
    _allow_all: bool
```

注解只给读者和类型检查器看，不会创建值；真正的值还是在 `__init__` 里赋。

## 7. 顺带：`setdefault`

`dict.setdefault(key, default)` 的语义是：

- key 已存在：返回原值，不覆盖；
- key 不存在：插入 default，并返回 default。

```python
d = {}
d.setdefault("a", 1)   # 返回 1，d = {"a": 1}
d.setdefault("a", 2)   # 返回 1，d 仍是 {"a": 1}
```

[`os.environ.setdefault(...)`](../../src/minicode/cli.py#L47) 用的是同一套语义：shell 里已有的环境变量不会被 `.env` 覆盖，包括值为空字符串的情况。

## 8. 最常见的几个错误

- 把实例属性写成局部变量：`mode = ...` 不会挂到 `self` 上。
- 方法签名忘了 `self`：`def f(x)` 通过实例调用时会多传一个参数。
- 用可变类属性当实例状态：`items = []` 会被所有实例共享。
- 以为 `_x` 是 private：它只是约定。
- 以为 `self.x` 需要声明：不需要；第一次赋值就创建，但没赋值就访问会报错。
- 以为 `setdefault` 会覆盖已有值：不会。

一句话：`self` 是实例，`__init__` 负责给它挂属性；类属性写在类体里、实例属性写在 `self` 上；Python 用命名约定而不是访问控制来区分 public/internal。
