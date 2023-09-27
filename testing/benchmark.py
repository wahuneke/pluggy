"""
Benchmarking and performance tests.
"""
import dataclasses
from textwrap import dedent
from typing import Mapping, Any

import pytest

from pluggy import HookimplMarker, HookCaller
from pluggy import HookspecMarker
from pluggy import PluginManager
from pluggy._callers import _multicall
from pluggy._hooks import HookImpl


hookspec = HookspecMarker("example")
hookimpl = HookimplMarker("example")


@hookimpl
def hook(arg1, arg2, arg3):
    return arg1, arg2, arg3


@hookimpl(wrapper=True)
def wrapper(arg1, arg2, arg3):
    return (yield)


@pytest.fixture(params=[10, 100], ids="hooks={}".format)
def hooks(request):
    return [hook for i in range(request.param)]


@pytest.fixture(params=[10, 100], ids="wrappers={}".format)
def wrappers(request):
    return [wrapper for i in range(request.param)]


class NewPluginManager(PluginManager):
    def do_compile(self):
        """When you're ready to enter turbo mode, run this. hook attribute will be replaced and can't be restored"""

        assert len(self.get_plugins()) == 5

        @dataclasses.dataclass
        class Caller:
            plugins: list

            def fun(self, hooks, nesting):

                result = []
                result.append(self.plugins[0].fun(hooks, nesting))
                result.append(self.plugins[1].fun(hooks, nesting))
                result.append(self.plugins[2].fun(hooks, nesting))
                result.append(self.plugins[3].fun(hooks, nesting))
                result.append(self.plugins[4].fun(hooks, nesting))

                return result

        self.hook = Caller(list(self.get_plugins()))


class NewerPluginManager(PluginManager):

    def do_compile(self):
        """When you're ready to enter turbo mode, run this. hook attribute will be replaced and can't be restored"""
        assert isinstance(self.hook.fun, HookCaller)
        code, symbols = self.hook.fun.as_code()
        compiled = compile(code, "", "exec")
        locs = {'plugins': list(self.get_plugins())} | symbols

        @dataclasses.dataclass
        class Caller:
            locs: Mapping
            ccc: Any

            def fun(self, hooks, nesting):
                as_code_output =[]
                exec(self.ccc, None, {'as_code_output': as_code_output, 'hooks': hooks, 'nesting': nesting} | self.locs)
                return as_code_output[0]

        self.hook = Caller(locs, compiled)


def test_hook_and_wrappers_speed(benchmark, hooks, wrappers):
    def setup():
        hook_name = "foo"
        hook_impls = []
        for method in hooks + wrappers:
            f = HookImpl(None, "<temp>", method, method.example_impl)
            hook_impls.append(f)
        caller_kwargs = {"arg1": 1, "arg2": 2, "arg3": 3}
        firstresult = False
        return (hook_name, hook_impls, caller_kwargs, firstresult), {}

    benchmark.pedantic(_multicall, setup=setup, rounds=10)


@pytest.mark.parametrize("impl", (
        PluginManager,
        # NewPluginManager,
        NewerPluginManager,
))
@pytest.mark.parametrize(
    ("plugins, wrappers, nesting"),
    [
        (1, 0, 0),
        (1, 1, 0),
        (1, 1, 1),
        (1, 1, 5),
        (1, 5, 1),
        (1, 5, 5),
        (5, 1, 1),
        (5, 1, 5),
        (5, 5, 1),
        (5, 5, 5),
        (20, 0, 0),
        (20, 0, 2),
        (20, 20, 0),
        (50, 50, 0),
        (100, 0, 0),
        (200, 0, 0),
    ],
    ids=lambda i: str(i).zfill(3)
)
def test_call_hook(benchmark, plugins, wrappers, nesting, impl):
    pm = impl("example")

    class HookSpec:
        @hookspec
        def fun(self, hooks, nesting: int):
            pass

    class Plugin:
        def __init__(self, num: int) -> None:
            self.num = num

        def __repr__(self) -> str:
            return f"<Plugin {self.num}>"

        @hookimpl
        def fun(self, hooks, nesting: int) -> None:
            if nesting:
                hooks.fun(hooks=hooks, nesting=nesting - 1)

    class PluginWrap:
        def __init__(self, num: int) -> None:
            self.num = num

        def __repr__(self) -> str:
            return f"<PluginWrap {self.num}>"

        @hookimpl(wrapper=True)
        def fun(self):
            return (yield)

    pm.add_hookspecs(HookSpec)

    for i in range(plugins):
        pm.register(Plugin(i), name=f"plug_{i}")
    for i in range(wrappers):
        pm.register(PluginWrap(i), name=f"wrap_plug_{i}")

    if hasattr(pm, 'do_compile'):
        pm.do_compile()

    # benchmark.group=f"{plugins}-{wrappers}"
    benchmark(pm.hook.fun, hooks=pm.hook, nesting=nesting)
