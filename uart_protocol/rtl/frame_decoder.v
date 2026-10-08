//==============================================================================
// frame_decoder.v -- 协议帧解码模块 v1.1（字节流 -> 帧, 支持多模块）
//------------------------------------------------------------------------------
// 帧格式:
//   [SOF1=0xAA][SOF2=0x55][CMD][MOD][IDX][LEN_L][LEN_H][PAYLOAD...][CRC_L][CRC_H]
//   * CMD 操作码  : 0x01 写 / 0x02 读 / 0x81 写应答 / 0x82 读应答
//   * MOD 模块类型: 0x01 SystemValue / 0x02 CheckParam / ... (由寄存器组表决定)
//   * IDX 实例索引: 多实例模块的通道号; 单实例模块固定 0
//   * LEN = payload 字节数(16bit 小端), 上限 MAX_PAYLOAD(默认512)
//   * CRC16-MODBUS: 初值 0xFFFF, 反射多项式 0xA001, 低字节先发
//     覆盖范围 = CMD+MOD+IDX+LEN+PAYLOAD (不含 SOF, 与 ARM 侧 C 实现一致)
//
// 特性  :
//   * 每时钟拍消费 1 字节, 输入接 FWFT 型字节 FIFO
//   * payload 存入内部 512x8 RAM, CRC 通过后由上层组合读出;
//     内容保持到下一帧 payload 写入为止(帧间隔 >> 上层搬运时间, 安全)
//   * 帧头假同步处理: S_SOF2 收到 SOF1 时保持滑动窗口(AA AA 55 可同步)
//   * 超长帧(len > MAX_PAYLOAD)丢弃并给出 err_len 脉冲
//==============================================================================
module frame_decoder #(
    parameter [7:0]   SOF1        = 8'hAA,
    parameter [7:0]   SOF2        = 8'h55,
    parameter integer MAX_PAYLOAD = 512
)(
    input  wire        clk,
    input  wire        rst_n,

    // ---- 字节流输入(接 FWFT 型 RX FIFO) ----
    output wire        fifo_rd,      // 本拍消费 1 字节
    input  wire [7:0]  fifo_dout,    // 队首字节(组合有效)
    input  wire        fifo_empty,

    // ---- 帧结果 ----
    output reg         frame_valid,  // 1 拍脉冲: 一帧 CRC 校验通过
    output reg  [7:0]  frame_cmd,    // 操作码
    output reg  [7:0]  frame_mod,    // 模块类型
    output reg  [7:0]  frame_idx,    // 实例索引(通道号)
    output reg  [15:0] frame_len,    // 本帧 payload 长度

    // ---- payload 存储(外部只读, 组合) ----
    input  wire [8:0]  payload_addr,
    output wire [7:0]  payload_q,

    // ---- 错误脉冲(各 1 拍, 可接 LED/计数器) ----
    output reg         err_len,      // payload 超长, 帧丢弃
    output reg         err_crc,      // CRC 校验失败, 帧丢弃

    // ---- 调试 ----
    output wire [3:0]  state
);

    localparam [3:0] S_SOF1 = 4'd0,
                     S_SOF2 = 4'd1,
                     S_CMD  = 4'd2,
                     S_MOD  = 4'd3,
                     S_IDX  = 4'd4,
                     S_LENL = 4'd5,
                     S_LENH = 4'd6,
                     S_PAYL = 4'd7,
                     S_CRCL = 4'd8,
                     S_CRCH = 4'd9;

    //-------------------------------------------------------------------------
    // CRC16-MODBUS 单字节组合函数(与 C 侧 crc16_update 逐字节等价)
    // 综合器展开为 8 级组合逻辑, 每拍处理 1 字节, 50MHz 无时序压力
    //-------------------------------------------------------------------------
    function [15:0] crc16_byte;
        input [15:0] c_in;
        input [7:0]  d;
        reg   [15:0] c;
        integer i;
        begin
            c = c_in ^ {8'h00, d};
            for (i = 0; i < 8; i = i + 1) begin
                if (c[0]) c = (c >> 1) ^ 16'hA001;
                else      c = (c >> 1);
            end
            crc16_byte = c;
        end
    endfunction

    reg [3:0]  state_r;
    reg [7:0]  cmd_r, mod_r, idx_r;
    reg [15:0] len_r;
    reg [15:0] byte_cnt;
    reg [15:0] crc_calc;
    reg [7:0]  crc_rx_lo;

    // payload RAM 512x8: 内部时序写 + 外部组合读(同域简单双口)
    reg [7:0] payload_mem [0:MAX_PAYLOAD-1];
    assign payload_q = payload_mem[payload_addr];

    wire [7:0] b    = fifo_dout;
    wire       adv  = !fifo_empty;          // 本拍消费一个字节

    assign fifo_rd = adv;
    assign state   = state_r;

    wire [15:0] crc_next = crc16_byte(crc_calc, b);   // CRC 覆盖字节更新值

    // S_LENH 拍得到的完整长度(寄存器尚未更新)
    wire [15:0] len_full = {b, len_r[7:0]};

    integer i;
    initial begin
        for (i = 0; i < MAX_PAYLOAD; i = i + 1)
            payload_mem[i] = 8'h00;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_r     <= S_SOF1;
            cmd_r       <= 8'h00;
            mod_r       <= 8'h00;
            idx_r       <= 8'h00;
            len_r       <= 16'd0;
            byte_cnt    <= 16'd0;
            crc_calc    <= 16'hFFFF;
            crc_rx_lo   <= 8'h00;
            frame_valid <= 1'b0;
            frame_cmd   <= 8'h00;
            frame_mod   <= 8'h00;
            frame_idx   <= 8'h00;
            frame_len   <= 16'd0;
            err_len     <= 1'b0;
            err_crc     <= 1'b0;
        end else begin
            frame_valid <= 1'b0;
            err_len     <= 1'b0;
            err_crc     <= 1'b0;
            if (adv) begin
                case (state_r)
                    S_SOF1: begin
                        if (b == SOF1)
                            state_r <= S_SOF2;          // 非 SOF1 字节直接丢弃
                    end
                    S_SOF2: begin
                        if (b == SOF2) begin
                            state_r  <= S_CMD;
                            crc_calc <= 16'hFFFF;       // 帧开始, CRC 复位
                        end else if (b == SOF1) begin
                            state_r <= S_SOF2;          // 滑动窗口: AA AA 55
                        end else begin
                            state_r <= S_SOF1;
                        end
                    end
                    S_CMD: begin
                        cmd_r    <= b;
                        crc_calc <= crc_next;
                        state_r  <= S_MOD;
                    end
                    S_MOD: begin
                        mod_r    <= b;
                        crc_calc <= crc_next;
                        state_r  <= S_IDX;
                    end
                    S_IDX: begin
                        idx_r    <= b;
                        crc_calc <= crc_next;
                        state_r  <= S_LENL;
                    end
                    S_LENL: begin
                        len_r[7:0] <= b;
                        crc_calc   <= crc_next;
                        state_r    <= S_LENH;
                    end
                    S_LENH: begin
                        len_r[15:8] <= b;
                        crc_calc    <= crc_next;
                        if (len_full > MAX_PAYLOAD) begin
                            err_len <= 1'b1;            // 超长帧, 丢弃
                            state_r <= S_SOF1;
                        end else if (len_full == 16'd0) begin
                            state_r <= S_CRCL;          // 空 payload(读请求)
                        end else begin
                            byte_cnt <= 16'd0;
                            state_r  <= S_PAYL;
                        end
                    end
                    S_PAYL: begin
                        payload_mem[byte_cnt[8:0]] <= b;
                        crc_calc <= crc_next;
                        if (byte_cnt + 16'd1 >= len_r)  // 最后一个 payload 字节
                            state_r <= S_CRCL;
                        byte_cnt <= byte_cnt + 16'd1;
                    end
                    S_CRCL: begin
                        crc_rx_lo <= b;
                        state_r   <= S_CRCH;
                    end
                    S_CRCH: begin
                        if ({b, crc_rx_lo} == crc_calc) begin
                            frame_valid <= 1'b1;
                            frame_cmd   <= cmd_r;
                            frame_mod   <= mod_r;
                            frame_idx   <= idx_r;
                            frame_len   <= len_r;
                        end else begin
                            err_crc <= 1'b1;            // CRC 错, 帧丢弃
                        end
                        state_r <= S_SOF1;              // 立即找下一帧(支持粘帧)
                    end
                    default: state_r <= S_SOF1;
                endcase
            end
        end
    end
endmodule
