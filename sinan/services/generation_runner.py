# sinan/services/generation_runner.py
import asyncio
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus

"""
Phase 1 的核心，模拟完整的 5 步生成流程（全部硬编码，无 LLM）。

流程：

receive — 更新 session 状态为 RUNNING，推送"接收需求"事件
analyze — 推送"分析需求"事件
design — 推送"设计页面结构"事件
code — 调用 _template_html(prompt) 生成硬编码 HTML，推送"生成页面"事件
verify — 推送"验证通过"事件
host（不计入步骤表）— 把 HTML 写入 PageVersion 表，更新 session 字段，推送托管完成事件，最后调用 publish_done 关闭 SSE
每个步骤都会：

调用 event_bus.publish 推送 SSE 事件
asyncio.sleep(0.5) 模拟耗时（Phase 2 替换为真实 LLM 调用）
调用 _write_step 写一条 GenSessionStep 记录到数据库
注意点：

_template_html 里有 f-string + CSS {{}} 的双括号写法，是为了转义 f-string 里的花括号，写出来的 HTML 里是单括号 {}，这是正常的。
_save_page 里 created_by 传 session_id，Phase 1 先这样，Phase 2 完善用户体系后再改。
"""


class GenerationRunner:

    async def start(self, session_id: str) -> None:
        """
        后台异步执行生成流程。
        由 generate 路由通过 asyncio.create_task 启动，不阻塞请求。
        """
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        # 步骤定义：(step_name, 推送给前端的消息)
        steps = [
            ("receive", "正在接收需求..."),
            ("analyze", "正在分析需求..."),
            ("design",  "正在设计页面结构..."),
            ("code",    "正在生成页面..."),
            ("verify",  "验证通过"),
        ]

        html = ""
        for step_name, message in steps:
            await event_bus.publish(session_id, step_name, {"message": message})
            await asyncio.sleep(0.5)  # 模拟耗时，Phase 2 替换为 LLM 调用
            await self._write_step(session_id, step_name, message)

            if step_name == "code":
                # code 步骤：生成硬编码 HTML
                session = await session_store.get(session_id)
                prompt = session.prompt if session else ""
                html = self._template_html(prompt)

        # 托管：写 page_version 表，更新 session
        marker = f"page_{session_id[:8]}"
        version = 1
        await self._save_page(marker, version, html, created_by=session_id)
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=f"/api/v1/page/{marker}",
        )

        # 推送托管完成事件，再关闭 SSE 流
        await event_bus.publish(
            session_id,
            "host",
            {"message": f"页面已生成，预览地址: /api/v1/page/{marker}", "url": f"/api/v1/page/{marker}"},
        )
        await event_bus.publish_done(session_id)

    async def _write_step(self, session_id: str, step: str, message: str) -> None:
        """把步骤执行记录写入 gen_session_step 表"""
        record = GenSessionStep(
            session_id=session_id,
            step=step,
            direction="output",
            output_data={"message": message},
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    async def _save_page(self, marker: str, version: int, html: str, created_by: str) -> None:
        """把生成的 HTML 存入 page_version 表"""
        record = PageVersion(
            marker=marker,
            version=version,
            html_content=html,
            status=PageStatus.PUBLISHED,
            created_by=created_by,
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    def _template_html(self, prompt: str) -> str:
        """
        Phase 1 硬编码 HTML 模板，把 prompt 嵌入标题。
        Phase 2 替换为 LLM 生成的真实 HTML。
        注意：CSS 里的花括号需要双写 {{}} 以转义 f-string。
        """
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>生成页面</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    margin: 0; padding: 40px; background: #f5f7fa; color: #333;
  }}
  .card {{
    background: #fff; border-radius: 12px; padding: 32px;
    box-shadow: 0 2px 12px rgba(0,0,0,.08); max-width: 800px; margin: 0 auto;
  }}
  h1 {{ font-size: 24px; margin-bottom: 8px; color: #1a1a2e; }}
  p  {{ color: #666; line-height: 1.6; }}
  .badge {{
    display: inline-block; background: #e8f4fd; color: #1677ff;
    padding: 4px 12px; border-radius: 20px; font-size: 13px; margin-top: 16px;
  }}
</style>
</head>
<body>
  <div class="card">
    <h1>Hello HTML</h1>
    <p>你的需求：<strong>{prompt}</strong></p>
    <p>这是 Phase 1 硬编码模板页面，Phase 2 将接入 LLM 生成真实内容。</p>
    <span class="badge">Phase 1 · 硬编码原型</span>
  </div>
</body>
</html>"""


# 模块级单例
generation_runner = GenerationRunner()