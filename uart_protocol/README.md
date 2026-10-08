# uart_protocol — SimpleSpray 串口协议引擎 (FPGA 侧) v1.1

UART 字节层 + 多模块帧协议解码/组包 + 统一字节地址寄存器组的完整 RTL 实现。
支持 `SystemValue`（单实例）与 `CheckParam`（每检测通道一份，可扩展到 20 通道）。

## 协议速览

```
AA 55 | CMD | MOD | IDX | LEN_L LEN_H | PAYLOAD[N] | CRC_L CRC_H
       └────────── CRC16-MODBUS 覆盖 ──────────────┘
```

| MOD | 模块 | 长度 | IDX |
|---|---|---|---|
| 0x01 | SystemValue | 51B | 固定 0 |
| 0x02 | CheckParam | 29B | 检测通道号 0~19 |

命令：`0x01` 写 / `0x02` 读 / `0x81` 写应答 / `0x82` 读应答

## 目录结构

```
uart_protocol/
├── rtl/
│   ├── uart_rx.v            串行->字节 (位中心采样)
│   ├── uart_tx.v            字节->串行 (valid/ready 握手)
│   ├── sync_fifo.v          FWFT 同步 FIFO
│   ├── frame_decoder.v      帧解码: 同步/CMD-MOD-IDX 解析/CRC16/512B payload RAM
│   ├── frame_encoder.v      帧组包: 快照/CRC16/FIFO 反压
│   ├── module_regfile.v     模块描述表 + 命令分发 + 所有权过滤 + 发送快照
│   └── uart_protocol_top.v  顶层集成
├── sim/
│   └── tb_uart_protocol.v   系统级 TB (9 个用例, 位级端到端回环)
└── doc/
    └── protocol_spec.md     协议规格书(偏移表/C 参考/扩展指南, 必读)
```

## 快速开始

### 仿真 (iverilog)

```bash
cd uart_protocol
iverilog -g2001 -o sim.vvp rtl/*.v sim/tb_uart_protocol.v
vvp sim.vvp
# 期望输出: === ALL TESTS PASSED ===
```

覆盖用例：SystemValue 写回读 / ACK 帧格式 / SystemValue 读回环 /
CheckParam 多通道写回读 / CheckParam 读回环 / 坏 CRC / 超长帧 /
非法模块 / 长度不符。

### 集成到工程

1. 将 `rtl/*.v` 加入工程源文件（**无第三方 IP 依赖**）
2. 顶层 `uart_protocol_top` 参数按板卡修改：
   - `CLK_FREQ` 实际系统时钟(Hz)、`BAUD` 波特率
   - `CHK_NUM` 检测通道数（默认 20）
3. 连接 `rxd/txd` 管脚与电平约束
4. 应用侧通过 `app_*` 字节地址总线读写字段时间；
   监听 `cfg_updated` / `cfg_field_we` / `soft_reset_strobe` 事件

## 关键约束（改代码前必读）

1. **C 结构体必须 `#pragma pack(1)`**
   - `SystemValue` 默认对齐 sizeof=**52**，packed=**51**
   - `CheckParam` 默认对齐 sizeof=**32**，packed=**29**
2. 协议参数改动需**四处同步**：`frame_decoder` + `frame_encoder` + TB + C 侧
3. 新增结构体 → 只改 `module_regfile.v` 的 `map_ok`/`map_base`/`map_len`
   （见规格书第 11 节）
4. 新增字段 → **只能尾部追加**，保持既有偏移不变
5. FP-owned 字段必须**整段**保护（多字节量高低字节不能只保护一半），
   RTL `is_fpga_owned` 与 TB 的 `owned_off[]` 表必须一致
6. `sys_mem` 改为 `mem[0:1023]` 统一地址空间后，所有字段访问改按**字节地址**
   （规格书第 7 节有地址映射图）

## 版本变更

| 版本 | 变更 |
|---|---|
| v1.0 | `AA 55 CMD LEN PAYLOAD CRC`；SystemValue 专用命名寄存器组 |
| **v1.1** | 帧头加 `MOD`+`IDX`；统一 1KB 字节地址空间 + 模块描述表；CheckParam 20 通道；status 增 `0x03` 非法模块；应答回显 MOD/IDX |
