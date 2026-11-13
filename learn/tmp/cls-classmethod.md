# `cls` 是什么

`cls` 是 `@classmethod` 自动传入的第一个参数：**调用这个方法的类本身**，不是实例。

```python
class PermissionMode(str, Enum):
    @classmethod
    def parse(cls, value): ...
```

调用 `PermissionMode.parse("ask")` 时，`cls` 就是 `PermissionMode`；调用 `SomeSubclass.parse("ask")` 时，`cls` 是 `SomeSubclass`。它和普通方法里的 `self` 对应：`self` 是实例，`cls` 是类。

在 [`PermissionMode.parse()`](../../src/minicode/policy.py#L18) 里：

- [`if isinstance(value, cls)`](../../src/minicode/policy.py#L20)：如果传入的已经是 `PermissionMode`（或它的子类）实例，直接返回，不重复构造。
- [`return cls(raw)`](../../src/minicode/policy.py#L24)：用字符串构造枚举成员。`cls` 是 `PermissionMode` 时，`PermissionMode("ask")` 返回 `PermissionMode.ASK`。
- [`for mode in cls`](../../src/minicode/policy.py#L26)：遍历枚举成员，也用 `cls`，所以换成子类时仍然跟着子类走。

`cls` 不是关键字，只是社区约定名；写成 `klass`、`mode_cls` 也可以，语义不变。用 `@classmethod` 而不是 `@staticmethod` 的原因是：方法需要知道“是哪个类在调用”，而不是把 `PermissionMode` 写死在函数体里。实际调用点在 argparse 的 [`type=PermissionMode.parse`](../../src/minicode/cli.py#L342)，argparse 只拿到字符串，没有实例，所以用类方法正合适。

一句话：`cls` 就是“当前这个类”，在这里等价于 `PermissionMode`。
