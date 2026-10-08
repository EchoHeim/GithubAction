//==============================================================================
// uart_tx.v -- UART 串行发送物理层（单字节并行接口 -> 串行位流）
//------------------------------------------------------------------------------
// 帧格式: 1 起始位(0) + 8 数据位(LSB first) + 1 停止位(1), 无校验位
// 握手  : tx_ready=1 时采样 tx_valid 并锁存 tx_byte（valid/ready 标准握手）
//==============================================================================
module uart_tx #(
    parameter integer CLK_FREQ = 50_000_000,
    parameter integer BAUD     = 115200
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] tx_byte,
    input  wire       tx_valid,
    output wire       tx_ready,
    output reg        txd
);
    localparam integer BIT_CYC = CLK_FREQ / BAUD;

    localparam [1:0] S_IDLE  = 2'd0,
                     S_START = 2'd1,
                     S_DATA  = 2'd2,
                     S_STOP  = 2'd3;

    reg [1:0]  state;
    reg [31:0] baud_cnt;
    reg [2:0]  bit_idx;
    reg [7:0]  shreg;

    assign tx_ready = (state == S_IDLE);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= S_IDLE;
            baud_cnt <= 32'd0;
            bit_idx  <= 3'd0;
            shreg    <= 8'h00;
            txd      <= 1'b1;
        end else begin
            case (state)
                S_IDLE: begin
                    txd <= 1'b1;
                    if (tx_valid) begin
                        shreg    <= tx_byte;
                        baud_cnt <= 32'd0;
                        state    <= S_START;
                    end
                end
                S_START: begin
                    txd <= 1'b0;
                    if (baud_cnt == BIT_CYC - 1) begin
                        baud_cnt <= 32'd0;
                        bit_idx  <= 3'd0;
                        state    <= S_DATA;
                    end else begin
                        baud_cnt <= baud_cnt + 32'd1;
                    end
                end
                S_DATA: begin
                    txd <= shreg[bit_idx];   // LSB first
                    if (baud_cnt == BIT_CYC - 1) begin
                        baud_cnt <= 32'd0;
                        if (bit_idx == 3'd7)
                            state <= S_STOP;
                        else
                            bit_idx <= bit_idx + 3'd1;
                    end else begin
                        baud_cnt <= baud_cnt + 32'd1;
                    end
                end
                S_STOP: begin
                    txd <= 1'b1;
                    if (baud_cnt == BIT_CYC - 1) begin
                        baud_cnt <= 32'd0;
                        state    <= S_IDLE;
                    end else begin
                        baud_cnt <= baud_cnt + 32'd1;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
