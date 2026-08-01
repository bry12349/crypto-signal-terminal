import { useEffect, useRef, useState, type FormEvent } from "react";
import { Bot, KeyRound, Send, WalletCards, X } from "lucide-react";

type Integration = "telegram" | "bot" | "dune" | null;

export function TelegramOnboarding() {
  const [active, setActive] = useState<Integration>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [qrImage, setQrImage] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload: Record<string, string | number> = {};
    for (const [key, value] of form.entries()) {
      if (!value) continue;
      payload[key] = key.endsWith("_id") || key.endsWith("query_id") ? Number(value) : String(value);
    }
    const response = await fetch("http://127.0.0.1:8765/api/v1/settings/credentials", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setMessage("保存失败，本地服务不可用");
      return;
    }
    formRef.current?.reset();
    if (active === "telegram") {
      const login = await fetch("http://127.0.0.1:8765/api/v1/telegram/login/qr", { method: "POST" });
      if (!login.ok) {
        setMessage("凭据已保存，但二维码生成失败");
        return;
      }
      const result = await login.json() as { status: string; qr_image: string | null };
      setQrImage(result.qr_image);
      setMessage(result.status === "authorized" ? "Telegram 已授权" : "请使用 Telegram 手机端扫码授权");
      return;
    }
    setMessage("已保存到本机安全存储");
  }

  useEffect(() => {
    if (!qrImage) return;
    const timer = window.setInterval(async () => {
      const response = await fetch("http://127.0.0.1:8765/api/v1/telegram/login/status");
      if (!response.ok) return;
      const result = await response.json() as { status: string };
      if (result.status === "authorized") {
        setQrImage(null);
        setMessage("Telegram 已授权，正在同步置顶频道");
      } else if (result.status === "expired" || result.status === "error") {
        setQrImage(null);
        setMessage("二维码已失效，请重新生成");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [qrImage]);

  return (
    <section className="integration-drawer">
      <div><span className="eyebrow">PRIVATE INTEGRATIONS</span><h2>本地数据连接</h2><p>凭据只发送到 127.0.0.1，并写入系统钥匙串；不会进入机会流、日志或回放数据。</p></div>
      <article><Send /><div><strong>Telegram 用户账号</strong><span>监控所有置顶频道</span></div><button aria-label="配置 Telegram" onClick={() => { setActive("telegram"); setMessage(null); }}>配置</button></article>
      <article><Bot /><div><strong>手机通知 Bot</strong><span>回传二次确认与订单建议</span></div><button aria-label="配置通知 Bot" onClick={() => { setActive("bot"); setMessage(null); }}>配置</button></article>
      <article><WalletCards /><div><strong>Dune 聪明钱</strong><span>可选链上钱包候选数据</span></div><button aria-label="配置 Dune" onClick={() => { setActive("dune"); setMessage(null); }}>配置</button></article>

      {active && (
        <form className="credential-form" ref={formRef} onSubmit={save}>
          <div className="form-head"><strong>{active === "telegram" ? "Telegram 用户连接" : active === "bot" ? "手机通知 Bot" : "Dune 链上数据"}</strong><button type="button" aria-label="关闭配置" onClick={() => setActive(null)}><X size={14} /></button></div>
          {active === "telegram" && <>
            <label>API ID<input name="telegram_api_id" inputMode="numeric" autoComplete="off" required /></label>
            <label>API Hash<input name="telegram_api_hash" type="password" autoComplete="off" required /></label>
            <p>保存后会在本机生成一次性登录二维码；请用 Telegram 手机端扫码授权。</p>
          </>}
          {active === "bot" && <>
            <label>Bot Token<input name="telegram_bot_token" type="password" autoComplete="off" required /></label>
            <label>Chat ID<input name="telegram_chat_id" autoComplete="off" required /></label>
          </>}
          {active === "dune" && <>
            <label>Dune API Key<input name="dune_api_key" type="password" autoComplete="off" required /></label>
            <label>Query ID<input name="dune_query_id" inputMode="numeric" autoComplete="off" required /></label>
          </>}
          <button className="save-credentials" type="submit">安全保存</button>
        </form>
      )}
      {qrImage && <div className="telegram-qr"><img src={qrImage} alt="Telegram 登录二维码" /><span>二维码约 2 分钟内有效</span></div>}
      {message && <div className="save-message">{message}</div>}
      <footer><KeyRound size={14} />敏感输入保存后会立即从表单清除</footer>
    </section>
  );
}
