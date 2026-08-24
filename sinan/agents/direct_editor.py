# -*- coding: UTF-8 -*-
"""直接编辑器 - 页面编辑流水线的第零阶段（Phase 0）。

拦截格式化的元素级修改指令，通过 BeautifulSoup 直接操作 DOM 完成修改，
完全绕过 LLM，实现毫秒级响应。仅当用户输入严格符合 「修改「#id」: 操作」
格式时才会触发，其余情况降级到后续分类流程。

支持的指令格式（修改「#id」: <操作>）：
  文案:       改为/改成/换成/设置为/设为/文案改为/文字改为/文本改为 <text>
  删除:       删除 | 移除 | 移除元素
  可见性:     显示/展示/设为可见 | 隐藏/设为隐藏 | 可见/visibility显示 | 不可见/visibility隐藏
  禁用/只读:  禁用 | 启用/取消禁用 | 设为只读/只读 | 取消只读/可编辑
              必填/设为必填 | 取消必填 | 选中/勾选 | 取消选中
  背景色:     背景色改为/背景颜色改为/背景设为/背景色换成 <value>
  文字颜色:   文字颜色改为/字体颜色改为/颜色改为/字色改为 <value>
  字体大小:   文字大小改为/字体大小改为/字号改为/font-size改为 <value>
  字重:       加粗/文字加粗 | 取消加粗/正常字重 | 字重改为 <value>
  字体样式:   斜体/文字斜体 | 取消斜体 | 字体改为/font-family改为 <value>
  文字装饰:   下划线/添加下划线 | 删除线/添加删除线 | 取消下划线/取消删除线
  宽高:       宽度改为/宽改为/width改为 | 高度改为/高改为/height改为 <value>
              最大/最小宽度改为 | 最大/最小高度改为 <value>
  间距:       内边距改为/padding改为 | 外边距改为/margin改为 <value>
  圆角:       圆角改为/border-radius改为 <value>
  透明度:     透明度改为/opacity改为 <value>
  边框:       边框改为/border改为/边框颜色改为 <value>
  对齐:       左对齐/文字左对齐 | 居中/水平居中 | 右对齐
  布局:       定位改为/position改为 | 层级改为/z-index改为 <value>
              overflow改为 | cursor改为/鼠标样式改为 <value>
  class:      添加/加上/增加/新增class <name> | 移除/去掉/删除/取消/去除class <name>
  属性:       链接改为/href改为/跳转地址改为 <url>
              图片改为/src改为/图片地址改为 <url>
              placeholder改为/占位文字改为/提示文字改为 <text>
              title改为/tooltip改为 | alt改为/图片描述改为
              name改为 | value改为/默认值改为 | target改为/链接打开方式改为 <value>
  兜底:       其余内容直接作为新文案写入
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

try:
    from bs4 import BeautifulSoup, NavigableString
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# 快速预检正则
# ---------------------------------------------------------------------------

# 匹配所有「修改「#<id>」: ...」格式的指令，不区分具体操作类型。
# 作为廉价的前置过滤器，在完整规则表匹配之前做一次粗筛；
# 同时在 HTTP 请求处理层作为早退出信号，跳过意图分类和迭代分类两次 LLM 调用。
DIRECT_EDIT_PRECHECK = re.compile(r"^修改「#\S+」\s*[:：]\s*.+$")

_RULES: list[dict] = [
    # ── 文案 ──────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*"
            r"(?:文案修改为|文案改为|文字改为|文字修改为|文本改为|文本修改为|修改为|改为|改成|换成|设置为|设为)"
            r"(.+)$"
        ),
        "action": "set_text",
    },
    # ── 删除 ──────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:删除|移除元素|移除)$"),
        "action": "remove_element",
    },
    # ── 可见性 ────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:显示|展示|设为可见)$"),
        "action": "set_style",
        "style_prop": "display",
        "force_value": "block",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:隐藏|设为隐藏)$"),
        "action": "set_style",
        "style_prop": "display",
        "force_value": "none",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:不可见|visibility隐藏)$"),
        "action": "set_style",
        "style_prop": "visibility",
        "force_value": "hidden",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:可见|visibility显示)$"),
        "action": "set_style",
        "style_prop": "visibility",
        "force_value": "visible",
    },
    # ── 禁用 / 启用 / 只读 ──────────────────────────────────────────────────────
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:禁用|设为禁用)$"),
        "action": "set_disabled",
        "force_value": True,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:启用|取消禁用|设为启用)$"),
        "action": "set_disabled",
        "force_value": False,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:设为只读|只读)$"),
        "action": "set_attr_bool",
        "attr": "readonly",
        "force_value": True,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:取消只读|可编辑)$"),
        "action": "set_attr_bool",
        "attr": "readonly",
        "force_value": False,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:必填|设为必填)$"),
        "action": "set_attr_bool",
        "attr": "required",
        "force_value": True,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:取消必填|非必填)$"),
        "action": "set_attr_bool",
        "attr": "required",
        "force_value": False,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:选中|勾选|设为选中)$"),
        "action": "set_attr_bool",
        "attr": "checked",
        "force_value": True,
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:取消选中|取消勾选)$"),
        "action": "set_attr_bool",
        "attr": "checked",
        "force_value": False,
    },
    # ── 颜色 / 背景 ────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*"
            r"(?:背景色改为|背景色设为|背景色修改为|背景颜色改为|背景颜色设为|背景设为|背景改为|背景色换成)"
            r"(.+)$"
        ),
        "action": "set_style",
        "style_prop": "background-color",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*"
            r"(?:文字颜色改为|文字颜色设为|字体颜色改为|字体颜色设为|颜色改为|颜色设为|颜色换成|字色改为)"
            r"(.+)$"
        ),
        "action": "set_style",
        "style_prop": "color",
    },
    # ── 字体 ──────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*"
            r"(?:文字大小改为|文字大小设为|字体大小改为|字体大小设为|字号改为|字号设为|font-size改为|font-size设为|字体大小换成)"
            r"(.+)$"
        ),
        "action": "set_style",
        "style_prop": "font-size",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:加粗|文字加粗|字体加粗)$"),
        "action": "set_style",
        "style_prop": "font-weight",
        "force_value": "bold",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:取消加粗|正常字重|字体正常)$"),
        "action": "set_style",
        "style_prop": "font-weight",
        "force_value": "normal",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:字重改为|字重设为|font-weight改为|font-weight设为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "font-weight",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:斜体|文字斜体|设为斜体)$"),
        "action": "set_style",
        "style_prop": "font-style",
        "force_value": "italic",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:取消斜体|正常字体样式)$"),
        "action": "set_style",
        "style_prop": "font-style",
        "force_value": "normal",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:字体改为|字体设为|font-family改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "font-family",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:下划线|添加下划线)$"),
        "action": "set_style",
        "style_prop": "text-decoration",
        "force_value": "underline",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:删除线|添加删除线)$"),
        "action": "set_style",
        "style_prop": "text-decoration",
        "force_value": "line-through",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:取消下划线|取消删除线|取消文字装饰)$"),
        "action": "set_style",
        "style_prop": "text-decoration",
        "force_value": "none",
    },
    # ── 尺寸 ──────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:宽度改为|宽度设为|宽改为|宽设为|width改为|width设为|宽度换成)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "width",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:高度改为|高度设为|高改为|高设为|height改为|height设为|高度换成)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "height",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:最大宽度改为|最大宽度设为|max-width改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "max-width",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:最小宽度改为|最小宽度设为|min-width改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "min-width",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:最大高度改为|最大高度设为|max-height改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "max-height",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:最小高度改为|最小高度设为|min-height改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "min-height",
    },
    # ── 间距 / 圆角 / 透明度 / 边框 ───────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:内边距改为|内边距设为|padding改为|padding设为|内距改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "padding",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:外边距改为|外边距设为|margin改为|margin设为|外距改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "margin",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:圆角改为|圆角设为|border-radius改为|border-radius设为|圆角换成)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "border-radius",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:透明度改为|透明度设为|opacity改为|opacity设为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "opacity",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:边框改为|边框设为|border改为|边框颜色改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "border",
    },
    # ── 布局 ──────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:左对齐|文字左对齐)$"),
        "action": "set_style",
        "style_prop": "text-align",
        "force_value": "left",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:居中|水平居中|文字居中)$"),
        "action": "set_style",
        "style_prop": "text-align",
        "force_value": "center",
    },
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(?:右对齐|文字右对齐)$"),
        "action": "set_style",
        "style_prop": "text-align",
        "force_value": "right",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:定位改为|position改为|position设为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "position",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:层级改为|z-index改为|z-index设为|层级设为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "z-index",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:overflow改为|溢出改为|溢出设为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "overflow",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:cursor改为|鼠标样式改为|鼠标改为)(.+)$"
        ),
        "action": "set_style",
        "style_prop": "cursor",
    },
    # ── class ─────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:添加class|加上class|增加class|新增class|添加样式类)\s+(\S+)$"
        ),
        "action": "add_class",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:移除class|去掉class|删除class|取消class|去除class)\s+(\S+)$"
        ),
        "action": "remove_class",
    },
    # ── 属性 ──────────────────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:链接改为|链接设为|href改为|href设为|链接地址改为|链接地址设为|跳转地址改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "href",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:图片改为|图片设为|src改为|src设为|图片地址改为|图片地址设为|图片路径改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "src",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:placeholder改为|placeholder设为|占位文字改为|占位文字设为|提示文字改为|提示文字设为|占位符改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "placeholder",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:title改为|title设为|标题属性改为|tooltip改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "title",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:alt改为|alt设为|图片描述改为|图片alt改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "alt",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:name改为|name设为|name属性改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "name",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:value改为|value设为|默认值改为|输入值改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "value",
    },
    {
        "pattern": re.compile(
            r"^修改「#(\S+)」\s*[:：]\s*(?:target改为|target设为|链接打开方式改为)(.+)$"
        ),
        "action": "set_attr",
        "attr": "target",
    },
    # ── 兜底：其余内容直接作为文案写入 ────────────────────────────────────────────
    {
        "pattern": re.compile(r"^修改「#(\S+)」\s*[:：]\s*(.+)$"),
        "action": "set_text",
    },
]


# ---------------------------------------------------------------------------
# DirectEditor
# ---------------------------------------------------------------------------

class DirectEditor:
    """第零阶段编辑器：将正则匹配到的指令直接转化为 DOM 变更。

    成功时返回修改后的 HTML 字符串；
    若指令不匹配任何规则或目标元素在 HTML 中不存在，则返回 None。
    """

    def try_edit(self, user_input: str, html: str) -> tuple[Optional[str], str]:
        """尝试对 HTML 执行直接编辑操作。

        按顺序遍历 _RULES 规则表，找到第一条匹配的规则后：
        1. 从正则捕获组中提取目标元素 id 和操作值；
        2. 若规则携带 force_value，则用固定值覆盖捕获组的值；
        3. 用 BeautifulSoup 解析 HTML，按 id 定位目标元素；
        4. 根据 action 类型执行对应的 DOM 变更；
        5. 将整个 soup 序列化回 HTML 字符串并返回。

        Args:
            user_input: 用户的原始指令文本，如「修改「#btn-submit」: 文案改为 提交」。
            html: 当前页面的完整 HTML 字符串。

        Returns:
            (result_html, source) 元组：
            - result_html: 修改后的 HTML 字符串，失败时为 None；
            - source: 操作结果标识，取值为：
                'direct_edit'        – 成功完成修改；
                'no_match'           – 指令未匹配到任何规则；
                'element_not_found'  – 规则命中但 HTML 中找不到对应 id 的元素；
                'bs4_unavailable'    – beautifulsoup4 未安装，无法执行 DOM 操作。
        """
        if not _BS4_AVAILABLE:
            return None, "bs4_unavailable"

        user_input = user_input.strip()

        for rule in _RULES:
            m = rule["pattern"].match(user_input)
            if not m:
                continue

            element_id = m.group(1)
            value: Optional[str] = m.group(2).strip() if m.lastindex >= 2 else None
            if "force_value" in rule:
                value = rule["force_value"]

            soup = BeautifulSoup(html, "html.parser")
            element = soup.find(id=element_id)
            if not element:
                return None, "element_not_found"

            action = rule["action"]

            if action == "set_text":
                # 清空元素的所有子节点，替换为单个纯文本节点
                element.clear()
                element.append(NavigableString(value))

            elif action == "remove_element":
                # 从 DOM 树中彻底移除该元素（含所有子节点）
                element.decompose()

            elif action == "set_style":
                prop = rule["style_prop"]
                existing = element.get("style", "") or ""
                # 先从现有 style 中移除同名属性声明，避免重复
                existing = re.sub(
                    rf"\b{re.escape(prop)}\s*:\s*[^;]+;?\s*", "", existing
                ).strip("; ")
                # 拼接新声明，有旧 style 时用分号隔开
                new_style = f"{existing};{prop}:{value};" if existing else f"{prop}:{value};"
                element["style"] = new_style

            elif action == "add_class":
                # 去重添加，避免同一 class 出现多次
                classes: list[str] = list(element.get("class") or [])
                if value not in classes:
                    classes.append(value)
                element["class"] = classes

            elif action == "remove_class":
                # 移除指定 class；若移除后列表为空则删除整个 class 属性
                classes = list(element.get("class") or [])
                if value in classes:
                    classes.remove(value)
                if classes:
                    element["class"] = classes
                else:
                    del element["class"]

            elif action == "set_attr":
                # 直接设置元素的指定 HTML 属性（href、src、placeholder 等）
                element[rule["attr"]] = value

            elif action == "set_disabled":
                # disabled 是布尔属性：存在即禁用，不存在即启用
                if rule["force_value"]:
                    element["disabled"] = ""
                else:
                    if "disabled" in element.attrs:
                        del element["disabled"]

            elif action == "set_attr_bool":
                # 处理 readonly、required、checked 等布尔属性：
                # True → 设置属性（空字符串值），False → 删除属性
                attr = rule["attr"]
                if rule["force_value"]:
                    element[attr] = ""
                else:
                    if attr in element.attrs:
                        del element[attr]

            return str(soup), "direct_edit"

        return None, "no_match"


# ---------------------------------------------------------------------------
# 会话级编辑锁
# ---------------------------------------------------------------------------

class _SessionLockRegistry:
    """为每个 session_id 维护一把独立的 asyncio.Lock。

    使用普通字典（强引用）存储锁对象，确保锁在注册表存续期间不会被 GC 回收。
    锁对象本身非常轻量；注册表的大小由并发活跃会话数决定，实际场景中数量很小。
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        # 元锁：保护 _locks 字典本身的读写，防止并发创建同一 session_id 的锁
        self._meta_lock = asyncio.Lock()

    async def _get_or_create(self, session_id: str) -> asyncio.Lock:
        """获取指定会话的锁，不存在时创建并注册。"""
        async with self._meta_lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock

    def lock_for(self, session_id: str) -> "_SessionLockContext":
        """返回一个异步上下文管理器，用于串行化同一会话内的编辑操作。

        用法：
            async with session_edit_locks.lock_for(session_id):
                # 此块内对该会话的编辑操作互斥执行
        """
        return _SessionLockContext(self, session_id)


class _SessionLockContext:
    """_SessionLockRegistry.lock_for() 返回的异步上下文管理器实现。"""

    def __init__(self, registry: _SessionLockRegistry, session_id: str) -> None:
        self._registry = registry
        self._session_id = session_id
        self._lock: Optional[asyncio.Lock] = None

    async def __aenter__(self) -> "_SessionLockContext":
        """进入上下文：获取（或创建）对应会话的锁并加锁。"""
        self._lock = await self._registry._get_or_create(self._session_id)
        await self._lock.acquire()
        return self

    async def __aexit__(self, *_) -> None:
        """退出上下文：释放锁。"""
        if self._lock is not None:
            self._lock.release()


# 全局单例注册表 —— 直接 import 使用
session_edit_locks = _SessionLockRegistry()

# 全局单例编辑器
direct_editor = DirectEditor()
