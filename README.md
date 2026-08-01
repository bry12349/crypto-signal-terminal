# Crypto Signal Terminal

一个本地优先的加密货币合约机会终端。它只保留会直接影响交易决策的证据：多周期趋势、主动成交、盘口失衡、持仓量变化、波动压缩、跨交易所价格确认、Telegram 社区信号和聪明钱候选。

## v0.1.0 已实现

- BTC / ETH 日内趋势跟随：4h 与 1h 定方向，15m 建立结构，5m 触发入场。
- 山寨币临界雷达：寻找低波动压缩、成交放大、OI 加速和盘口/主动流同向的起爆或瀑布前状态。
- 聪明钱候选：只有大额订单流跨窗口持续、OI 同时增长且形成价格冲击或吸收时才显示；不会把单笔大单直接称为聪明钱。
- Telegram 二次确认：本机二维码登录用户账号，自动发现全部置顶频道，监听新消息、编辑和删除；收到交易信号后立即重新拉取公开市场数据并独立计算结论。
- 手机回推：通过 Telegram Bot 返回确认/条件确认/拒绝/过期结论，以及重新计算的入场、止损、分批止盈、盈亏比和有效期。
- 订单建议：给出市价单、限价单或止损市价触发建议和固定风险仓位；v0.1.0 只准备模拟订单，不连接交易所私钥，也不会自动提交真实订单。
- 本地安全：Telegram API Hash、StringSession、Bot Token 和 Dune Key 保存到 macOS 钥匙串，不进入前端状态、日志、回放或 Git。

行情取自公开 API。Bybit 提供合约价格、K 线、盘口、主动成交和 OI，OKX 用于跨交易所价格确认；Dune 是可选的链上钱包候选来源。

## 本地开发

```bash
cd /Users/a0000/crypto-signal-terminal
./scripts/bootstrap.sh
./scripts/run-demo.sh
```

另一个终端启动界面：

```bash
cd /Users/a0000/crypto-signal-terminal/desktop
pnpm dev
```

打开设置，保存 Telegram API ID / API Hash 后，软件会生成一次性二维码。用 Telegram 手机端进入“设置 → 设备 → 连接桌面设备”扫码。再配置 Bot Token 和接收消息的 Chat ID，即可启用手机回推。

## 构建 macOS 应用

```bash
cd /Users/a0000/crypto-signal-terminal
./scripts/build-sidecar.sh
cd desktop
pnpm tauri build
```

构建产物位于 `desktop/src-tauri/target/release/bundle/`。当前构建目标为 Apple Silicon macOS。

## 风险边界

这是决策支持软件，不保证预测准确。交易建议有数据时效和滑点上限，数据陈旧、结构不完整或盈亏比不足时会拒绝给单。真实资金执行必须由使用者确认；高杠杆可能迅速造成全部保证金损失。
