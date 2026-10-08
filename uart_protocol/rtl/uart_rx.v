//==============================================================================
// uart_rx.v -- UART 串行接收物理层（串行位流 -> 单字节并行接口）
//------------------------------------------------------------------------------
// 帧格式: 1 起始位(0) + 8 数据位(LSB first) + 1 停止位(1), 无校验位
// 采样  : 边沿检测起始位, 位中心采样（时钟过采样方式, 无需波特率时钟）
// 接口  : rx_byte/rx_valid 为 1 拍脉冲输出, 上层直接写入字节 FIFO
//==============================================================================
module uart_rx #(
    parameter integer CLK_FREQ = 50_000_000,   // 系统时钟 Hz
    parameter integer BAUD     = 115200        // 波特率
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rxd,
    output reg  [7:0] rx_byte,
    output reg        rx_valid
);
    localparam integer BIT_CYC = CLK_FREQ / BAUD;   // 每 bit 时钟数

    localparam [1:0] S_IDLE  = 2'd0,
                     S_START = 2'd1,
                     S_DATA  = 2'd2,
                     S_STOP  = 2'd3;

    // 两级同步 + 下降沿检测
    reg [1:0] rx_sync;
    reg       rxd_fall;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_sync  <= 2'b11;
            rxd_fall <= 1'b0;
        end else begin
            rx_sync  <= {rx_sync[0], rxd};
            rxd_fall <= rx_sync[1] & ~rx_sync[0];
        end
    end

    reg [1:0]  state;
    reg [31:0] baud_cnt;
    reg [2:0]  bit_idx;
    reg [7:0]  shreg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= S_IDLE;
            baud_cnt <= 32'd0;
            bit_idx  <= 3'd0;
            shreg    <= 8'h00;
            rx_byte  <= 8'h00;
            rx_valid <= 1'b0;
        end else begin
            rx_valid <= 1'b0;
            case (state)
                S_IDLE: begin
                    if (rxd_fall) begin
                        state    <= S_START;
                        baud_cnt <= 32'd0;
                    end
                end
                S_START: begin
                    // 到起始位中点再确认, 滤除毛刺
                    if (baud_cnt == BIT_CYC/2 - 1) begin
                        if (rx_sync[1] == 1'b0) begin
                            baud_cnt <= 32'd0;
                            bit_idx  <= 3'd0;
                            state    <= S_DATA;
                        end else begin
                            state <= S_IDLE;   // 毛刺, 回空闲
                        end
                    end else begin
                        baud_cnt <= baud_cnt + 32'd1;
                    end
                end
                S_DATA: begin
                    if (baud_cnt == BIT_CYC - 1) begin
                        baud_cnt <= 32'd0;
                        shreg    <= {rx_sync[1], shreg[7:1]};  // LSB first
                        if (bit_idx == 3'd7)
                            state <= S_STOP;
                        else
                            bit_idx <= bit_idx + 3'd1;
                    end else begin
                        baud_cnt <= baud_cnt + 32'd1;
                    end
                end
                S_STOP: begin
                    if (baud_cnt == BIT_CYC - 1) begin
                        if (rx_sync[1] == 1'b1) begin   // 停止位合法
                            rx_byte  <= shreg;
                            rx_valid <= 1'b1;
                        end
                        state <= S_IDLE;                // 帧错误也丢弃
                    end else begin
                        baud_cnt <= baud_cnt + 32'd1;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
