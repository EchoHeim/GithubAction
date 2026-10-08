//==============================================================================
// frame_encoder.v -- 协议帧组包发送模块 v1.1（帧 -> 字节流, 支持多模块）
//------------------------------------------------------------------------------
// 帧格式: [SOF1][SOF2][CMD][MOD][IDX][LEN_L][LEN_H][PAYLOAD...][CRC_L][CRC_H]
//   CRC16-MODBUS 覆盖 CMD+MOD+IDX+LEN+PAYLOAD, 与 frame_decoder 完全对称
//
// 数据流: start 触发(带 cmd/mod/idx/len) -> src_req 请求寄存器组准备快照
//         -> 逐字节写 TX FIFO(帧头/长度/payload/CRC)
// 反压  : TX FIFO 满时状态冻结等待, 不会丢字节
//==============================================================================
module frame_encoder #(
    parameter [7:0] SOF1 = 8'hAA,
    parameter [7:0] SOF2 = 8'h55
)(
    input  wire        clk,
    input  wire        rst_n,

    // ---- 启动(1 拍脉冲) ----
    input  wire        start,
    input  wire [7:0]  cmd,
    input  wire [7:0]  mod,
    input  wire [7:0]  idx,
    input  wire [15:0] payload_len,    // 本帧 payload 字节数

    // ---- payload 源(寄存器组快照, 组合读) ----
    output reg         src_req,        // 请求源准备(快照)
    input  wire        src_ready,      // 源就绪脉冲
    output reg  [8:0]  src_addr,       // 源读地址
    input  wire [7:0]  src_dout,

    // ---- 写 TX FIFO ----
    output wire        fifo_wr,
    output wire [7:0]  fifo_din,
    input  wire        fifo_full,

    // ---- 状态 ----
    output wire        busy,
    output reg         done            // 组包完成脉冲
);
    localparam [3:0] E_IDLE = 4'd0,
                     E_WAIT = 4'd1,    // 等待快照就绪
                     E_SOF1 = 4'd2,
                     E_SOF2 = 4'd3,
                     E_CMD  = 4'd4,
                     E_MOD  = 4'd5,
                     E_IDX  = 4'd6,
                     E_LENL = 4'd7,
                     E_LENH = 4'd8,
                     E_PAYL = 4'd9,
                     E_CRCL = 4'd10,
                     E_CRCH = 4'd11;

    //-------------------------------------------------------------------------
    // CRC16-MODBUS 单字节组合函数(与 frame_decoder 相同)
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

    reg [3:0]  state;
    reg [7:0]  cmd_r, mod_r, idx_r;
    reg [15:0] len_r;
    reg [15:0] cnt;
    reg [15:0] crc_calc;

    assign busy = (state != E_IDLE);

    // 当前状态要发送的字节(组合)
    reg [7:0] wr_byte;
    always @* begin
        case (state)
            E_SOF1:  wr_byte = SOF1;
            E_SOF2:  wr_byte = SOF2;
            E_CMD:   wr_byte = cmd_r;
            E_MOD:   wr_byte = mod_r;
            E_IDX:   wr_byte = idx_r;
            E_LENL:  wr_byte = len_r[7:0];
            E_LENH:  wr_byte = len_r[15:8];
            E_PAYL:  wr_byte = src_dout;
            E_CRCL:  wr_byte = crc_calc[7:0];
            E_CRCH:  wr_byte = crc_calc[15:8];
            default: wr_byte = 8'h00;
        endcase
    end

    // 只有"发字节"状态才产生写请求, FIFO 满则冻结
    reg wr_state;
    always @* begin
        wr_state = 1'b0;
        case (state)
            E_SOF1, E_SOF2, E_CMD, E_MOD, E_IDX, E_LENL, E_LENH,
            E_PAYL, E_CRCL, E_CRCH:
                wr_state = 1'b1;
            default: ;
        endcase
    end

    assign fifo_wr  = wr_state && !fifo_full;
    assign fifo_din = wr_byte;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= E_IDLE;
            cmd_r    <= 8'h00;
            mod_r    <= 8'h00;
            idx_r    <= 8'h00;
            len_r    <= 16'd0;
            cnt      <= 16'd0;
            crc_calc <= 16'hFFFF;
            src_addr <= 9'd0;
            src_req  <= 1'b0;
            done     <= 1'b0;
        end else begin
            src_req <= 1'b0;
            done    <= 1'b0;
            case (state)
                E_IDLE: begin
                    if (start) begin
                        cmd_r   <= cmd;
                        mod_r   <= mod;
                        idx_r   <= idx;
                        len_r   <= payload_len;
                        src_req <= 1'b1;
                        state   <= E_WAIT;
                    end
                end
                E_WAIT: begin
                    if (src_ready) begin
                        crc_calc <= 16'hFFFF;
                        src_addr <= 9'd0;
                        cnt      <= 16'd0;
                        state    <= E_SOF1;
                    end
                end
                E_SOF1: if (!fifo_full) state <= E_SOF2;
                E_SOF2: if (!fifo_full) state <= E_CMD;
                E_CMD: if (!fifo_full) begin
                    crc_calc <= crc16_byte(crc_calc, wr_byte);
                    state    <= E_MOD;
                end
                E_MOD: if (!fifo_full) begin
                    crc_calc <= crc16_byte(crc_calc, wr_byte);
                    state    <= E_IDX;
                end
                E_IDX: if (!fifo_full) begin
                    crc_calc <= crc16_byte(crc_calc, wr_byte);
                    state    <= E_LENL;
                end
                E_LENL: if (!fifo_full) begin
                    crc_calc <= crc16_byte(crc_calc, wr_byte);
                    state    <= E_LENH;
                end
                E_LENH: if (!fifo_full) begin
                    crc_calc <= crc16_byte(crc_calc, wr_byte);
                    if (len_r == 16'd0)
                        state <= E_CRCL;      // 空 payload 帧直接补 CRC
                    else
                        state <= E_PAYL;
                end
                E_PAYL: if (!fifo_full) begin
                    crc_calc <= crc16_byte(crc_calc, wr_byte);
                    src_addr <= src_addr + 9'd1;
                    cnt      <= cnt + 16'd1;
                    if (cnt + 16'd1 == len_r)
                        state <= E_CRCL;      // 最后一个 payload 字节
                end
                E_CRCL: if (!fifo_full) state <= E_CRCH;
                E_CRCH: if (!fifo_full) begin
                    done  <= 1'b1;
                    state <= E_IDLE;
                end
                default: state <= E_IDLE;
            endcase
        end
    end
endmodule
