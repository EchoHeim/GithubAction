//==============================================================================
// sync_fifo.v -- 同步 FIFO（FWFT 模式：队首数据组合常有效）
//------------------------------------------------------------------------------
// 用途  : RX 侧缓存 uart_rx 字节流（解耦物理层与协议层）
//         TX 侧缓存组包整帧字节（encoder 突发写入, uart_tx 匀速读出）
// 说明  : 单时钟域; 二进制指针（同域无需格雷码）;
//         上电 initial 清零, FPGA 综合时由 bitstream 初始化
//==============================================================================
module sync_fifo #(
    parameter integer DW = 8,    // 数据位宽
    parameter integer AW = 6     // 地址位宽, 深度 = 2**AW
)(
    input  wire          clk,
    input  wire          rst_n,
    input  wire          wr_en,
    input  wire [DW-1:0] din,
    input  wire          rd_en,
    output wire [DW-1:0] dout,
    output wire          empty,
    output wire          full,
    output wire [AW:0]   count
);
    reg [DW-1:0] mem [0:(1<<AW)-1];

    reg [AW:0] wptr, rptr;

    assign empty = (wptr == rptr);
    assign full  = (wptr[AW] != rptr[AW]) && (wptr[AW-1:0] == rptr[AW-1:0]);
    assign dout  = mem[rptr[AW-1:0]];    // FWFT: 组合输出队首
    assign count = wptr - rptr;

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    integer i;
    initial begin
        for (i = 0; i < (1 << AW); i = i + 1)
            mem[i] = {DW{1'b0}};
        wptr = {(AW+1){1'b0}};
        rptr = {(AW+1){1'b0}};
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr <= {(AW+1){1'b0}};
            rptr <= {(AW+1){1'b0}};
        end else begin
            if (do_wr) begin
                mem[wptr[AW-1:0]] <= din;
                wptr <= wptr + 1'b1;
            end
            if (do_rd) begin
                rptr <= rptr + 1'b1;
            end
        end
    end
endmodule
