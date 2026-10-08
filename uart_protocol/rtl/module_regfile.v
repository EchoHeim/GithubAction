//==============================================================================
// module_regfile.v -- 多模块统一寄存器组 + 命令分发（协议层核心, v1.1）
//------------------------------------------------------------------------------
// 设计思路:
//   把"每一个结构体一组命名寄存器"改为"统一字节地址空间 + 模块描述表"。
//   新增结构体(CheckParam/喷枪参数/剔除参数...)只需在描述表里加一条映射,
//   不必再展开一堆命名信号——这是支持多模块、多通道的关键。
//
// 地址空间布局(可由 parameter 调整):
//   0x000 .. 0x03F : SystemValue        51B (64B 窗口)
//   0x040 ..      : CheckParam 数组     每通道 32B 步进, 有效 29B
//                    base = 64 + IDX*32, IDX = 0..CHK_NUM-1
//   CHK_NUM=20 时峰值占用 64+640=704B -> ADDR_W=10(1KB)
//
// 职责:
//   1. 命令分发: WR(0x01) 搬运 payload 入库 / RD(0x02) 触发组包回传
//   2. 字段所有权过滤: FPGA 产生的运行量拒绝 ARM 回写, 防覆盖实时采样值
//   3. 发送快照: 逐字节拷贝目标模块到快照缓冲, 保证多字节字段原子性
//   4. 应用总线: app_wr/app_rd 字节级读写, 供业务逻辑更新动态量/读参数
//
// 状态码(status 字节):
//   0x00 OK / 0x01 LEN 与模块长度不符 / 0x02 命令未定义 / 0x03 模块或索引非法
//==============================================================================
module module_regfile #(
    parameter integer CHK_NUM      = 20,        // 检测通道数
    parameter integer ADDR_W       = 10,        // 字节地址位宽
    // ---- 模块类型标识 ----
    parameter [7:0]   MOD_SYSVAL   = 8'h01,     // SystemValue  单实例
    parameter [7:0]   MOD_CHKPARAM = 8'h02,     // CheckParam   多实例(通道)
    // ---- 模块长度(packed 字节数) ----
    parameter integer SYSVAL_LEN   = 51,
    parameter integer CHK_LEN      = 29,
    // ---- 地址映射 ----
    parameter integer SYSVAL_BASE  = 0,
    parameter integer CHK_BASE     = 64,
    parameter integer CHK_STRIDE   = 32,        // 每通道步进(建议 2 的幂)
    // ---- 命令字 ----
    parameter [7:0]   CMD_WR       = 8'h01,
    parameter [7:0]   CMD_RD       = 8'h02,
    parameter [7:0]   CMD_ACK_WR   = 8'h81,
    parameter [7:0]   CMD_RD_ACK   = 8'h82,
    parameter         ACK_ON_WRITE = 1
)(
    input  wire        clk,
    input  wire        rst_n,

    // ---- 来自 frame_decoder ----
    input  wire        frame_valid,
    input  wire [7:0]  frame_cmd,
    input  wire [7:0]  frame_mod,
    input  wire [7:0]  frame_idx,
    input  wire [15:0] frame_len,
    output wire [8:0]  pld_addr,          // 读 decoder payload RAM
    input  wire [7:0]  pld_dout,

    // ---- 到 frame_encoder ----
    output reg         enc_start,
    output reg  [7:0]  enc_cmd,
    output reg  [7:0]  enc_mod,
    output reg  [7:0]  enc_idx,
    output reg  [15:0] enc_len,
    input  wire        src_req,           // encoder 请求快照
    output reg         src_ready,         // 快照/ACK 就绪脉冲
    input  wire [8:0]  src_addr,
    output wire [7:0]  src_dout,

    // ---- 应用侧总线(业务逻辑) ----
    input  wire        app_wr_en,
    input  wire [ADDR_W-1:0] app_wr_addr,
    input  wire [7:0]  app_wr_data,
    input  wire [ADDR_W-1:0] app_rd_addr,
    output wire [7:0]  app_rd_dout,

    // ---- 事件输出 ----
    output reg         cfg_updated,       // 整包搬运完成脉冲
    output reg  [7:0]  cfg_mod,           // 本次更新的模块类型
    output reg  [7:0]  cfg_idx,           // 本次更新的实例号
    output reg         cfg_field_we,      // 搬运期间每字节写入脉冲
    output reg  [ADDR_W-1:0] cfg_field_addr,  // 对应字节地址
    output reg         soft_reset_strobe  // SystemValue SoftReset(0x05)写入
);
    localparam [ADDR_W-1:0] SYSVAL_BASE_A = SYSVAL_BASE;
    localparam [ADDR_W-1:0] CHK_BASE_A    = CHK_BASE;

    //-------------------------------------------------------------------------
    // 模块描述表(新增模块只改这里)
    //   map_ok  : 模块+索引组合是否合法
    //   map_base: 该模块在地址空间的起始字节地址
    //   map_len : 该模块 packed 长度
    //-------------------------------------------------------------------------
    function map_ok;
        input [7:0] m;
        input [7:0] i;
        begin
            case (m)
                MOD_SYSVAL  : map_ok = (i == 8'd0);          // 单实例
                MOD_CHKPARAM: map_ok = (i < CHK_NUM);        // i = 通道号
                default     : map_ok = 1'b0;
            endcase
        end
    endfunction

    function [ADDR_W-1:0] map_base;
        input [7:0] m;
        input [7:0] i;
        begin
            case (m)
                MOD_SYSVAL  : map_base = SYSVAL_BASE_A;
                MOD_CHKPARAM: map_base = CHK_BASE_A + (i * CHK_STRIDE);
                default     : map_base = {ADDR_W{1'b0}};
            endcase
        end
    endfunction

    function [15:0] map_len;
        input [7:0] m;
        begin
            case (m)
                MOD_SYSVAL  : map_len = SYSVAL_LEN;
                MOD_CHKPARAM: map_len = CHK_LEN;
                default     : map_len = 16'd0;
            endcase
        end
    endfunction

    //-------------------------------------------------------------------------
    // 字段所有权过滤: FPGA 产生的运行量只允许应用侧写, ARM 帧搬运时跳过
    // 第二参数为"模块内偏移", 不是全局地址
    //-------------------------------------------------------------------------
    function is_fpga_owned;
        input [7:0] m;
        input [7:0] o;
        begin
            is_fpga_owned = 1'b0;
            case (m)
                MOD_SYSVAL: begin
                    case (o)
                        8'h09,                              // CurPressure    ADC 采样
                        8'h0B,                              // TempPressure   显示刷新
                        8'h23, 8'h24,                       // TempRunSpeed
                        8'h29, 8'h2A,                       // RotationSpeed_MotorVal
                        8'h2B, 8'h2C,                       // CurErrNumber
                        8'h2D, 8'h2E,                       // CurRejectedNum
                        8'h2F, 8'h30, 8'h31, 8'h32:         // CurCheckNumber (32bit)
                            is_fpga_owned = 1'b1;
                        default: ;
                    endcase
                end
                MOD_CHKPARAM: begin
                    case (o)
                        8'h02: is_fpga_owned = 1'b1;        // CheckType 硬件类型(只读)
                        // TODO 待确认: 学习/测量结果字段是否也由 FPGA 回填
                        // 8'h01 (CheckLevel bit[7:4] 学习等级),
                        // 8'h11,8'h12 (Roll_NO_Glue_Value 滚胶无胶基准),
                        // 8'h13..8'h18 (Set_MaxSG/Set_MinSG/PercentSG)
                        default: ;
                    endcase
                end
                default: ;
            endcase
        end
    endfunction

    //-------------------------------------------------------------------------
    // 存储
    //-------------------------------------------------------------------------
    reg [7:0] mem [0:(1<<ADDR_W)-1];      // 统一寄存器组(异步读, 分布式 RAM)
    reg [7:0] snap_buf [0:63];            // 发送快照缓冲(容纳最大模块)

    reg [7:0]  ack_code;
    reg        tx_ack_sel;

    // ---- 搬运上下文 ----
    localparam [0:0] C_IDLE = 1'b0, C_COPY = 1'b1;
    reg        cst;
    reg [7:0]  c_mod, c_idx;
    reg [5:0]  caddr;
    reg [15:0] c_len;
    reg [ADDR_W-1:0] c_base;

    // ---- 快照上下文 ----
    localparam [0:0] P_IDLE = 1'b0, P_SNAP = 1'b1;
    reg        pst;
    reg [5:0]  p_cnt;
    reg [5:0]  tx_len6;
    reg [ADDR_W-1:0] tx_base;

    assign app_rd_dout = mem[app_rd_addr];
    assign pld_addr    = {3'd0, caddr};
    assign src_dout    = tx_ack_sel ? ack_code : snap_buf[src_addr[5:0]];

    integer i;
    initial begin
        for (i = 0; i < (1 << ADDR_W); i = i + 1)
            mem[i] = 8'h00;
        for (i = 0; i < 64; i = i + 1)
            snap_buf[i] = 8'h00;
    end

    //-------------------------------------------------------------------------
    // 寄存器组写入: 搬运优先(且跳过 FP-owned), 应用写其次
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        if (cst == C_COPY && !is_fpga_owned(c_mod, caddr))
            mem[c_base + caddr] <= pld_dout;
        else if (app_wr_en)
            mem[app_wr_addr] <= app_wr_data;
    end

    //-------------------------------------------------------------------------
    // 命令分发 + payload 搬运
    //-------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cst               <= C_IDLE;
            c_mod             <= 8'h00;
            c_idx             <= 8'h00;
            caddr             <= 6'd0;
            c_len             <= 16'd0;
            c_base            <= {ADDR_W{1'b0}};
            ack_code          <= 8'h00;
            tx_ack_sel        <= 1'b0;
            enc_start         <= 1'b0;
            enc_cmd           <= 8'h00;
            enc_mod           <= 8'h00;
            enc_idx           <= 8'h00;
            enc_len           <= 16'd0;
            cfg_updated       <= 1'b0;
            cfg_mod           <= 8'h00;
            cfg_idx           <= 8'h00;
            cfg_field_we      <= 1'b0;
            cfg_field_addr    <= {ADDR_W{1'b0}};
            soft_reset_strobe <= 1'b0;
        end else begin
            enc_start         <= 1'b0;
            cfg_updated       <= 1'b0;
            cfg_field_we      <= 1'b0;
            soft_reset_strobe <= 1'b0;

            case (cst)
                //-------------------------------------------------------------
                C_IDLE: begin
                    if (frame_valid) begin
                        if (frame_cmd == CMD_WR) begin
                            if (!map_ok(frame_mod, frame_idx)) begin
                                ack_code <= 8'h03;         // 模块/索引非法
                                if (ACK_ON_WRITE) begin
                                    enc_start   <= 1'b1;
                                    enc_cmd     <= CMD_ACK_WR;
                                    enc_mod     <= frame_mod;
                                    enc_idx     <= frame_idx;
                                    enc_len     <= 16'd1;
                                    tx_ack_sel  <= 1'b1;
                                end
                            end else if (frame_len != map_len(frame_mod)) begin
                                ack_code <= 8'h01;         // 长度错
                                if (ACK_ON_WRITE) begin
                                    enc_start   <= 1'b1;
                                    enc_cmd     <= CMD_ACK_WR;
                                    enc_mod     <= frame_mod;
                                    enc_idx     <= frame_idx;
                                    enc_len     <= 16'd1;
                                    tx_ack_sel  <= 1'b1;
                                end
                            end else begin
                                cst    <= C_COPY;
                                c_mod  <= frame_mod;
                                c_idx  <= frame_idx;
                                c_len  <= frame_len;
                                c_base <= map_base(frame_mod, frame_idx);
                                caddr  <= 6'd0;
                                ack_code <= 8'h00;         // OK
                            end
                        end else if (frame_cmd == CMD_RD) begin
                            if (map_ok(frame_mod, frame_idx)) begin
                                enc_start  <= 1'b1;
                                enc_cmd    <= CMD_RD_ACK;
                                enc_mod    <= frame_mod;
                                enc_idx    <= frame_idx;
                                enc_len    <= map_len(frame_mod);
                                tx_ack_sel <= 1'b0;
                            end else begin
                                ack_code <= 8'h03;
                                enc_start  <= 1'b1;
                                enc_cmd    <= CMD_ACK_WR;
                                enc_mod    <= frame_mod;
                                enc_idx    <= frame_idx;
                                enc_len    <= 16'd1;
                                tx_ack_sel <= 1'b1;
                            end
                        end else begin
                            ack_code <= 8'h02;             // 命令未定义
                            if (ACK_ON_WRITE) begin
                                enc_start  <= 1'b1;
                                enc_cmd    <= CMD_ACK_WR;
                                enc_mod    <= frame_mod;
                                enc_idx    <= frame_idx;
                                enc_len    <= 16'd1;
                                tx_ack_sel <= 1'b1;
                            end
                        end
                    end
                end
                //-------------------------------------------------------------
                C_COPY: begin
                    cfg_field_we   <= 1'b1;
                    cfg_field_addr <= c_base + caddr;
                    if ((c_mod == MOD_SYSVAL) && (caddr == 8'h05))
                        soft_reset_strobe <= 1'b1;   // SoftReset 字段写入
                    if (caddr + 16'd1 >= c_len) begin
                        cst         <= C_IDLE;
                        cfg_updated <= 1'b1;
                        cfg_mod     <= c_mod;
                        cfg_idx     <= c_idx;
                        if (ACK_ON_WRITE) begin
                            enc_start  <= 1'b1;
                            enc_cmd    <= CMD_ACK_WR;
                            enc_mod    <= c_mod;
                            enc_idx    <= c_idx;
                            enc_len    <= 16'd1;
                            tx_ack_sel <= 1'b1;
                        end
                    end else begin
                        caddr <= caddr + 6'd1;
                    end
                end
                default: cst <= C_IDLE;
            endcase
        end
    end

    //-------------------------------------------------------------------------
    // 发送快照: 逐字节拷贝目标模块 -> snap_buf, 保证多字节字段原子性
    //   拷贝 len 拍(≤51), 期间寄存器更新不影响本帧内容
    //   ACK 路径(1 字节)不走快照, 直接给 src_ready
    //-------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            src_ready <= 1'b0;
            pst       <= P_IDLE;
            p_cnt     <= 6'd0;
            tx_len6   <= 6'd0;
            tx_base   <= {ADDR_W{1'b0}};
        end else begin
            src_ready <= 1'b0;
            case (pst)
                P_IDLE: begin
                    if (src_req) begin
                        if (tx_ack_sel) begin
                            src_ready <= 1'b1;        // ACK: 1 字节, 无需快照
                        end else begin
                            tx_base <= map_base(enc_mod, enc_idx);
                            tx_len6 <= enc_len[5:0];
                            p_cnt   <= 6'd0;
                            pst     <= P_SNAP;
                        end
                    end
                end
                P_SNAP: begin
                    snap_buf[p_cnt] <= mem[tx_base + p_cnt];
                    if (p_cnt + 6'd1 >= tx_len6) begin
                        pst       <= P_IDLE;
                        src_ready <= 1'b1;
                    end
                    p_cnt <= p_cnt + 6'd1;
                end
                default: pst <= P_IDLE;
            endcase
        end
    end
endmodule
