# SimpleSpray 串口协议规格书

版本: **v1.1**（多模块多通道） | 日期: 2026-10-08 | 状态: **待用户签核**
v1.0 → v1.1 变更: 帧头增加 `MOD`/`IDX` 两字节，支持任意数量结构体与通道；
寄存器组改为统一字节地址空间 + 模块描述表。

---

## 1. 物理层与链路层参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| 接口 | UART 全双工, TTL 电平 | rxd / txd |
| 帧格式 | 8N1（1 起始 + 8 数据 LSB first + 1 停止） | 无奇偶校验 |
| 波特率 | 115200 | RTL 参数 `BAUD` |
| 时钟 | 50MHz 单时钟域 | RTL 参数 `CLK_FREQ` 必须与实际一致 |
| 帧长 | payload ≤ 512 字节 | 超长帧丢弃并置 `err_len` |

## 2. 协议帧格式 v1.1

```
┌──────┬──────┬──────┬──────┬──────┬───────┬───────┬─────────────┬───────┬───────┐
│ SOF1 │ SOF2 │ CMD  │ MOD  │ IDX  │ LEN_L │ LEN_H │  PAYLOAD[N] │ CRC_L │ CRC_H │
│ 0xAA │ 0x55 │ 1B   │ 1B   │ 1B   │       │       │  N ≤ 512B   │  1B   │  1B   │
└──────┴──────┴──────┴──────┴──────┴───────┴───────┴─────────────┴───────┴───────┘
└──────────────── CRC16-MODBUS 覆盖范围（不含 SOF）────────────────────────────┘
```

| 字段 | 含义 |
|---|---|
| CMD | 操作码：`0x01` 写 / `0x02` 读 / `0x81` 写应答 / `0x82` 读应答 |
| **MOD** | **模块类型**：`0x01` SystemValue / `0x02` CheckParam / … |
| **IDX** | **实例索引**：多实例模块的通道号；单实例模块固定 `0x00` |
| LEN | 16 位小端，payload 字节数（不含帧头与 CRC） |
| CRC16-MODBUS | 初值 `0xFFFF`，反射多项式 `0xA001`，**低字节先发** |

帧开销固定 9 字节（2 SOF + 5 头 + 2 CRC）。

### 为什么用 MOD + IDX 两个字节（而不是一个）

| 方案 | 结论 |
|---|---|
| 单字节 `MOD = 类型<<4 \| 通道` | 通道号只有 4bit → 最多 15 通道，**与本项目 20 通道规划冲突** |
| 单字节 MOD + 通道号放 payload | 通道号要占 payload 偏移 0，破坏"结构体原样映射"，C 侧要手工裁剪 |
| **MOD + IDX 两字节（采用）** | 通道号 8bit（≤255）、类型与实例解耦；新增模块类型不必重排通道号 |

代价是每帧多 1 字节开销（29~51 字节 payload 下约 2~3%），可接受。

## 3. 模块描述表

| MOD | 模块名 | LEN(packed) | IDX 含义 | 地址区间 |
|---|---|---|---|---|
| `0x01` | SystemValue | 51 | 固定 0 | `0x000` ~ `0x032` |
| `0x02` | CheckParam | 29 | 检测通道号 0 ~ CHK_NUM-1 | `64 + IDX×32` ~ `+28` |
| `0x03` | （预留）喷枪参数 | -- | -- | -- |
| `0x04` | （预留）剔除参数 | -- | -- | -- |
| `0x05` | （预留）条码参数 | -- | -- | -- |

`CHK_NUM` 默认 20（4 块 ARM × 5 通道规划）。

## 4. SystemValue 字段偏移表（packed = 51 字节）

> ⚠️ **C 侧必须 `#pragma pack(1)`**。默认对齐时 `SensorType`（0x14）后有 1 字节填充，
> sizeof = **52**，与 FPGA 映射错位。

| 偏移 | 长度 | 字段 | 所有权 |
|---|---|---|---|
| 0x00 | 1 | OS_Ver | ARM |
| 0x01 | 1 | FPGA_Ver1 | ARM |
| 0x02 | 1 | FPGA_Ver2 | ARM |
| 0x03 | 1 | BL1300_CodeInit | ARM |
| 0x04 | 1 | flag_ReadADC | ARM |
| 0x05 | 1 | SoftReset | ARM（写入产生 `soft_reset_strobe`） |
| 0x06 | 1 | flag_DataChange | ARM |
| 0x07 | 1 | flag_debugStatus | ARM |
| 0x08 | 1 | flag_debugStatus_hold | ARM |
| 0x09 | 1 | CurPressure | **FPGA** |
| 0x0A | 1 | SetPressure | ARM |
| 0x0B | 1 | TempPressure | **FPGA** |
| 0x0C | 1 | RejectCompVal | ARM |
| 0x0D | 1 | FlushSwitch | ARM |
| 0x0E | 1 | SetAutoSwitch | ARM |
| 0x0F | 1 | AlarmTime | ARM |
| 0x10 | 1 | Reject_Shutdown | ARM |
| 0x11 | 1 | ErrorThreshold | ARM |
| 0x12 | 1 | RotationDir | ARM |
| 0x13 | 1 | RotationSpeed | ARM |
| 0x14 | 1 | SensorType | ARM |
| 0x15 | 2 | ProductLength | ARM |
| 0x17 | 2 | ResponseLength | ARM |
| 0x19 | 2 | SensorDis | ARM |
| 0x1B | 2 | Compensate | ARM |
| 0x1D | 2 | Flush_Low_16 | ARM |
| 0x1F | 2 | Flush_High_16 | ARM |
| 0x21 | 2 | RunSpeed | ARM |
| 0x23 | 2 | TempRunSpeed | **FPGA** |
| 0x25 | 2 | RejectSpeed | ARM |
| 0x27 | 2 | RejectSpeed_Hold | ARM |
| 0x29 | 2 | RotationSpeed_MotorVal | **FPGA** |
| 0x2B | 2 | CurErrNumber | **FPGA** |
| 0x2D | 2 | CurRejectedNum | **FPGA** |
| 0x2F | 4 | CurCheckNumber | **FPGA** |

**FPGA-owned 字节清单（共 14 字节，RTL `is_fpga_owned` 与之对应）**：
`0x09, 0x0B, 0x23~0x24, 0x29~0x2A, 0x2B~0x2C, 0x2D~0x2E, 0x2F~0x32`

> 多字节量必须**整段**纳入保护。只保护低字节会造成高位被 ARM 覆盖、
> 计数器低位 FPGA 维护的混合状态——这是隐蔽且致命的错误。

## 5. CheckParam 字段偏移表（packed = 29 字节，每通道一份）

> ⚠️ **默认对齐时 sizeof = 32**：13 个 `int8u` 后补 1 字节（→14），
> `PercentSG` 为 `float` 需 4 字节对齐（→28），合计 32。
> 协议按 **packed = 29** 映射，C 侧必须 `#pragma pack(1)`。

| 偏移 | 长度 | 字段 | 所有权 | 说明 |
|---|---|---|---|---|
| 0x00 | 1 | ChkSwitch | ARM | bit6 学习模板 / bit5 纸张类型 / bit4 学习状态 / bit3 无胶区 / bit2 胶量 / bit1 产品长度 / bit0 检测开关 |
| 0x01 | 1 | CheckLevel | ARM | bit[7:4] 学习等级 / bit[3:0] 识别等级 |
| 0x02 | 1 | CheckType | **FPGA** | 硬件自识别型号（0x00 未连接 / 0xF1 GJC-800 / 0xF2 GJC-800A / 0xFC PJC-800 / 0x01~GUN_NUM 喷枪通道） |
| 0x03 | 1 | ProductSec | ARM | 产品段数 |
| 0x04 | 1 | FilterSec | ARM | 分段标准 4/8/16 |
| 0x05 | 1 | PercentMax | ARM | 胶量百分比最大值 |
| 0x06 | 1 | PercentMin | ARM | 胶量百分比最小值 |
| 0x07 | 1 | LenTolerance | ARM | 产品长度偏差 |
| 0x08 | 1 | NoGlueVal | ARM | 无胶区误差 |
| 0x09 | 1 | MaxDefect | ARM | 最大缺陷 |
| 0x0A | 1 | DefectComp | ARM | 缺陷补偿 |
| 0x0B | 1 | RollHighPrecisionEN | ARM | 滚胶高精度检测使能 |
| 0x0C | 1 | TriggerPort | ARM | bit[7:4] 0 内部/1 外部4光电/2 喷枪光电；bit[3:0] 端口号 |
| 0x0D | 2 | TrigPortDis | ARM | 光电偏移 |
| 0x0F | 2 | SensorRejectDis | ARM | 检测头到剔除光电距离 |
| 0x11 | 2 | SensorChkLen | ARM | 学习产品长度 |
| 0x13 | 2 | Roll_NO_Glue_Value | **待定** | 滚胶无胶基准值（学习结果，建议 FPGA） |
| 0x15 | 2 | Set_MaxSG | **待定** | 学习/统计结果，建议 FPGA |
| 0x17 | 2 | Set_MinSG | **待定** | 学习/统计结果，建议 FPGA |
| 0x19 | 4 | PercentSG | **待定** | float，建议 FPGA |

> **待你确认**：0x13~0x1C 这 10 字节若确为"学习/测量结果由 FPGA 产生"，
> 请在 `module_regfile.v` 的 `is_fpga_owned`（MOD_CHKPARAM 分支）中取消注释。
> 默认当前**只保护 0x02 CheckType**。

### float 字段传输提示

`PercentSG` 按 IEEE-754 单精度、小端 4 字节传输。跨平台建议：
- 若精度要求 ≤0.01%，ARM 侧改用**定点整数**（如 ×100 存 `int16u`）更省心；
- 若必须传 float，务必确认两端都是 IEEE-754 且位序一致（ARM/x86 均满足）。

## 6. 命令与应答

| CMD | 方向 | LEN | 含义 |
|---|---|---|---|
| `0x01` WR | ARM→FPGA | 模块长度 | 整包下发，成功后回 ACK(status=0) |
| `0x02` RD | ARM→FPGA | 0 | 读请求 |
| `0x81` ACK_WR | FPGA→ARM | 1 | payload = status（见下） |
| `0x82` RD_ACK | FPGA→ARM | 模块长度 | payload = 该模块快照 |
| 其他 | -- | -- | 回 ACK(status=2) |

**status 状态码**：

| 值 | 含义 |
|---|---|
| `0x00` | OK |
| `0x01` | LEN 与模块长度不符（帧被丢弃，寄存器组未改动） |
| `0x02` | 命令字未定义 |
| `0x03` | MOD 未定义或 IDX 越界 |

**应答帧回显请求的 MOD/IDX**，ARM 可据此关联请求、支持流水线多请求。

## 7. 地址空间映射（FPGA 内部，应用总线使用）

```
0x000 ┌────────────────────────────────┐
      │ SystemValue (51B, 窗口 64B)     │
0x03F └────────────────────────────────┘
0x040 ┌────────────────────────────────┐
      │ CheckParam[0]  29B (步进 32B)   │
0x05F ├────────────────────────────────┤
      │ CheckParam[1]                   │
0x07F ├────────────────────────────────┤
      │ ...                             │
      │ CheckParam[19]  → 0x2BF         │
0x2BF └────────────────────────────────┘
```

- 每通道步进 32B（29B 有效 + 3B 保留），地址 = `64 + IDX×32`（移位实现，无乘法器）
- 峰值占用 704B → `ADDR_W = 10`（1KB），预留扩展空间
- 应用侧按**字节地址**读写；读 16/32 位值时自行拼字节

## 8. 模块清单

| 文件 | 模块 | 职责 |
|---|---|---|
| `rtl/uart_rx.v` | uart_rx | 串行→字节，位中心采样 |
| `rtl/uart_tx.v` | uart_tx | 字节→串行，valid/ready 握手 |
| `rtl/sync_fifo.v` | sync_fifo | FWFT 同步 FIFO（RX 64B / TX 512B） |
| `rtl/frame_decoder.v` | frame_decoder | 帧头同步/滑窗、CMD/MOD/IDX 解析、CRC16、payload RAM |
| `rtl/frame_encoder.v` | frame_encoder | 组帧（含 MOD/IDX）、CRC16、FIFO 反压 |
| `rtl/module_regfile.v` | module_regfile | **模块描述表**、命令分发、所有权过滤、发送快照 |
| `rtl/uart_protocol_top.v` | uart_protocol_top | 顶层集成 |

顶层应用接口：

```verilog
// 字节地址总线（ADDR_W=10）
app_wr_en / app_wr_addr[9:0] / app_wr_data[7:0]
app_rd_addr[9:0] / app_rd_dout[7:0]

// 事件
cfg_updated        // 整包搬运完成脉冲
cfg_mod[7:0]       // 本次更新的模块类型
cfg_idx[7:0]       // 本次更新的实例号（通道）
cfg_field_we       // 搬运期间每个字节的写入脉冲
cfg_field_addr[9:0]// 对应写入地址（可用于识别任意字段写入事件）
soft_reset_strobe  // SystemValue 0x05 写入（便利输出）
err_crc / err_len  // 错误帧脉冲
```

事件用法示例：

```verilog
// 检测"任意通道的 CheckParam 被更新"
if (cfg_updated && cfg_mod == 8'h02) begin
    ch_param_base <= CHK_BASE + cfg_idx * CHK_STRIDE;
end

// 替代 soft_reset_strobe 的通用写法
if (cfg_field_we && cfg_field_addr == 10'h005) do_reset();
```

## 9. 时序与资源

**时序假设（重要）**
1. payload RAM 由 decoder 持有，`frame_valid` 后内容保持到下一帧 payload 写入。
   搬运 51 拍（≈1µs @50MHz），下一帧最早 87µs 后到达 → 余量 80 倍以上。
2. 发送快照**逐字节**拷贝（≤51 拍），保证 32 位计数等高字节原子性。
   相比 v1.0 的"一拍全量拷贝"，多花 ≤1µs，换取对 RAM 型存储的适配。
3. 解码器每拍消费 1 字节（50MB/s）≫ 到达速率（11.5KB/s），RX FIFO 64 深度不溢出。
4. TX FIFO 512 深度容纳整帧（最大 60B），encoder 含 full 反压，不丢字节。

**资源预估（CHK_NUM=20，Trion/Titanium 量级）**

| 资源 | 预估值 | 说明 |
|---|---|---|
| LUT | ~900 ~ 1500 | 主体：1024B 异步读寄存器组（双读口） + CRC 组合 + 状态机 |
| FF | ~700 | 状态机/指针/快照缓冲(64B)/payload 地址 |
| 分布式 RAM | 1024×8 | 统一寄存器组（**若器件紧张可改 BRAM，代价是快照改多拍**） |
| BRAM | 1 个 | TX FIFO 512×8（或 payload RAM 512×8） |

## 10. ARM 侧 C 参考实现

```c
#include <stdint.h>
#include <string.h>

/* ============ 协议常量 ============ */
#define PROTO_SOF1      0xAA
#define PROTO_SOF2      0x55
#define CMD_WR          0x01
#define CMD_RD          0x02
#define CMD_ACK_WR      0x81
#define CMD_RD_ACK      0x82

#define MOD_SYSVAL      0x01
#define MOD_CHKPARAM    0x02

/* ============ 结构体（必须 packed） ============ */
#pragma pack(1)
typedef struct {                    /* 51B */
    uint8_t  OS_Ver;                /* 0x00 */
    uint8_t  FPGA_Ver1;             /* 0x01 */
    uint8_t  FPGA_Ver2;             /* 0x02 */
    uint8_t  BL1300_CodeInit;       /* 0x03 */
    uint8_t  flag_ReadADC;          /* 0x04 */
    uint8_t  SoftReset;             /* 0x05 */
    uint8_t  flag_DataChange;       /* 0x06 */
    uint8_t  flag_debugStatus;      /* 0x07 */
    uint8_t  flag_debugStatus_hold; /* 0x08 */
    uint8_t  CurPressure;           /* 0x09 FPGA */
    uint8_t  SetPressure;           /* 0x0A */
    uint8_t  TempPressure;          /* 0x0B FPGA */
    uint8_t  RejectCompVal;         /* 0x0C */
    uint8_t  FlushSwitch;           /* 0x0D */
    uint8_t  SetAutoSwitch;         /* 0x0E */
    uint8_t  AlarmTime;             /* 0x0F */
    uint8_t  Reject_Shutdown;       /* 0x10 */
    uint8_t  ErrorThreshold;        /* 0x11 */
    uint8_t  RotationDir;           /* 0x12 */
    uint8_t  RotationSpeed;         /* 0x13 */
    uint8_t  SensorType;            /* 0x14 */
    uint16_t ProductLength;         /* 0x15 */
    uint16_t ResponseLength;        /* 0x17 */
    uint16_t SensorDis;             /* 0x19 */
    uint16_t Compensate;            /* 0x1B */
    uint16_t Flush_Low_16;          /* 0x1D */
    uint16_t Flush_High_16;         /* 0x1F */
    uint16_t RunSpeed;              /* 0x21 */
    uint16_t TempRunSpeed;          /* 0x23 FPGA */
    uint16_t RejectSpeed;           /* 0x25 */
    uint16_t RejectSpeed_Hold;      /* 0x27 */
    uint16_t RotationSpeed_MotorVal;/* 0x29 FPGA */
    uint16_t CurErrNumber;          /* 0x2B FPGA */
    uint16_t CurRejectedNum;        /* 0x2D FPGA */
    uint32_t CurCheckNumber;        /* 0x2F FPGA */
} SystemValue;

typedef struct {                    /* 29B */
    uint8_t  ChkSwitch;             /* 0x00 */
    uint8_t  CheckLevel;            /* 0x01 */
    uint8_t  CheckType;             /* 0x02 FPGA */
    uint8_t  ProductSec;            /* 0x03 */
    uint8_t  FilterSec;             /* 0x04 */
    uint8_t  PercentMax;            /* 0x05 */
    uint8_t  PercentMin;            /* 0x06 */
    uint8_t  LenTolerance;          /* 0x07 */
    uint8_t  NoGlueVal;             /* 0x08 */
    uint8_t  MaxDefect;             /* 0x09 */
    uint8_t  DefectComp;            /* 0x0A */
    uint8_t  RollHighPrecisionEN;   /* 0x0B */
    uint8_t  TriggerPort;           /* 0x0C */
    uint16_t TrigPortDis;           /* 0x0D */
    uint16_t SensorRejectDis;       /* 0x0F */
    uint16_t SensorChkLen;          /* 0x11 */
    uint16_t Roll_NO_Glue_Value;    /* 0x13 */
    uint16_t Set_MaxSG;             /* 0x15 */
    uint16_t Set_MinSG;             /* 0x17 */
    float    PercentSG;             /* 0x19 */
} CheckParam;
#pragma pack()

/* ============ CRC16-MODBUS ============ */
uint16_t crc16_update(uint16_t crc, const uint8_t *p, uint16_t n)
{
    while (n--) {
        uint8_t i;
        crc ^= *p++;
        for (i = 0; i < 8; i++)
            crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : (crc >> 1);
    }
    return crc;
}

/* ============ 组帧发送 ============ */
int proto_send(uint8_t cmd, uint8_t mod, uint8_t idx,
               const uint8_t *payload, uint16_t len)
{
    uint8_t  hdr[7] = {PROTO_SOF1, PROTO_SOF2, cmd, mod, idx,
                       (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
    uint8_t  tail[2];
    uint16_t crc = 0xFFFF;

    crc = crc16_update(crc, &hdr[2], 5);       /* CMD+MOD+IDX+LEN */
    if (len) crc = crc16_update(crc, payload, len);
    tail[0] = (uint8_t)(crc & 0xFF);           /* 低字节先发 */
    tail[1] = (uint8_t)(crc >> 8);

    uart_write(hdr, 7);
    if (len) uart_write(payload, len);
    uart_write(tail, 2);
    return 0;
}

/* 便捷封装 */
int proto_wr_sys(const SystemValue *v)
{ return proto_send(CMD_WR, MOD_SYSVAL, 0, (const uint8_t *)v, sizeof(*v)); }

int proto_rd_sys(void)
{ return proto_send(CMD_RD, MOD_SYSVAL, 0, NULL, 0); }

int proto_wr_chk(uint8_t ch, const CheckParam *p)
{ return proto_send(CMD_WR, MOD_CHKPARAM, ch, (const uint8_t *)p, sizeof(*p)); }

int proto_rd_chk(uint8_t ch)
{ return proto_send(CMD_RD, MOD_CHKPARAM, ch, NULL, 0); }
```

**接收状态机**（伪代码）：

```text
WAIT_SOF1: b==0xAA -> WAIT_SOF2
WAIT_SOF2: b==0x55 -> CMD;  b==0xAA 停留;  否则回 WAIT_SOF1
CMD/MOD/IDX/LENL/LENH: 逐字节收; len>512 或 len>预期上限 -> 回 WAIT_SOF1
PAYLOAD:   收 len 字节
CRC_L/H:   校验; 通过 -> 按 (cmd, mod, idx) 分发; 失败丢弃
```

**超时重传**：发 WR/RD 后启 100ms 定时器，未收到对应 ACK（按 MOD/IDX 匹配）
则重发，3 次失败报通信故障。

## 11. 如何新增一个模块或字段

**新增模块（例如"喷枪参数" MOD=0x03）**：
1. `module_regfile.v`：
   - 加参数 `MOD_GUNPARAM = 8'h03`、`GUN_LEN`、`GUN_BASE`、`GUN_STRIDE`
   - `map_ok` 加分支 `MOD_GUNPARAM: map_ok = (i < GUN_NUM);`
   - `map_base` / `map_len` 各加一条
   - 地址空间表里分配区间，确认不超过 `1<<ADDR_W`
   - 若含 FPGA 产生的字段，在 `is_fpga_owned` 加保护
2. C 侧加 `#pragma pack(1)` 结构体 + 偏移表
3. 本规格书第 3、7 节补一行
4. TB 加一组 WR/RD 回环用例

**新增字段**：只允许**尾部追加**（保持既有偏移不变，向后兼容）；
若插入中间字段，必须同步升级版本号并在两端同时上线。

## 12. 已知限制与假设

1. ARM 为唯一主机，FPGA 不主动上报。如需报警主动上报，需增加上行命令 +
   总线仲裁（当前 encoder 单请求串行，改动可控）。
2. 错误帧静默丢弃 + ACK 报错，无重传；链路可靠性依赖 ARM 超时重传。
3. 单请求串行：FPGA 同一时刻只处理一帧写入/一次组包。
   在 115200 下帧间隔 ≫ 处理时间，无需请求队列；若提高波特率需复评。
4. 应用总线为字节级随机访问，无突发/流水。
   高频读取建议把关键字段（如 `SetPressure`）单独拉线到顶层。
5. `flag_DataChange` 的按位语义由 ARM 侧解释，FPGA 仅透传存储。
6. CheckParam 0x13~0x1C（学习/测量结果）所有权待确认，当前默认归 ARM。
