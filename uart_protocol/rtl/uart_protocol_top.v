//==============================================================================
// uart_protocol_top.v -- 串口协议引擎顶层 v1.1（多模块多通道）
//------------------------------------------------------------------------------
// 集成: uart_rx -> RX FIFO(64) -> frame_decoder -> module_regfile
//       module_regfile <-> frame_encoder -> TX FIFO(512) -> uart_tx
// 时钟: 单时钟域 clk(默认 50MHz), UART 由 clk 过采样, 无 CDC
// 协议: AA 55 CMD MOD IDX LEN_L LEN_H PAYLOAD CRC_L CRC_H
//==============================================================================
module uart_protocol_top #(
    parameter integer CLK_FREQ   = 50_000_000,
    parameter integer BAUD       = 115200,
    parameter integer CHK_NUM    = 20,        // 检测通道数
    parameter [7:0]   MOD_SYSVAL = 8'h01,
    parameter [7:0]   MOD_CHKPARAM = 8'h02,
    parameter [7:0]   CMD_WR_SYS = 8'h01,
    parameter [7:0]   CMD_RD_SYS = 8'h02,
    parameter [7:0]   CMD_ACK_WR = 8'h81,
    parameter [7:0]   CMD_RD_ACK = 8'h82
)(
    input  wire        clk,
    input  wire        rst_n,

    // ---- UART 物理接口 ----
    input  wire        rxd,
    output wire        txd,

    // ---- 应用侧总线(统一字节地址空间) ----
    input  wire        app_wr_en,
    input  wire [9:0]  app_wr_addr,
    input  wire [7:0]  app_wr_data,
    input  wire [9:0]  app_rd_addr,
    output wire [7:0]  app_rd_dout,

    // ---- 事件 ----
    output wire        cfg_updated,       // 任一模块整包更新完成
    output wire [7:0]  cfg_mod,
    output wire [7:0]  cfg_idx,
    output wire        cfg_field_we,      // 搬运期间每字节写入脉冲
    output wire [9:0]  cfg_field_addr,
    output wire        soft_reset_strobe, // SystemValue SoftReset 写入

    // ---- 调试 ----
    output wire        err_crc,           // CRC 错帧脉冲
    output wire        err_len,           // 超长帧脉冲
    output wire [3:0]  dec_state          // 解码器状态
);
    //-------------------------------------------------------------------------
    // RX 物理层 + RX FIFO
    //-------------------------------------------------------------------------
    wire [7:0] rx_byte;
    wire       rx_valid;

    uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD(BAUD)) u_rx (
        .clk(clk), .rst_n(rst_n),
        .rxd(rxd), .rx_byte(rx_byte), .rx_valid(rx_valid)
    );

    wire [7:0] rx_fifo_dout;
    wire       rx_fifo_empty, rx_fifo_full;
    wire       rx_fifo_rd;

    sync_fifo #(.DW(8), .AW(6)) u_rx_fifo (      // 64 深度
        .clk(clk), .rst_n(rst_n),
        .wr_en(rx_valid), .din(rx_byte),
        .rd_en(rx_fifo_rd), .dout(rx_fifo_dout),
        .empty(rx_fifo_empty), .full(rx_fifo_full), .count()
    );

    //-------------------------------------------------------------------------
    // 帧解码
    //-------------------------------------------------------------------------
    wire        frame_valid;
    wire [7:0]  frame_cmd, frame_mod, frame_idx;
    wire [15:0] frame_len;
    wire [8:0]  pld_addr;
    wire [7:0]  pld_dout;

    frame_decoder #(.SOF1(8'hAA), .SOF2(8'h55), .MAX_PAYLOAD(512)) u_dec (
        .clk(clk), .rst_n(rst_n),
        .fifo_rd(rx_fifo_rd), .fifo_dout(rx_fifo_dout), .fifo_empty(rx_fifo_empty),
        .frame_valid(frame_valid), .frame_cmd(frame_cmd),
        .frame_mod(frame_mod), .frame_idx(frame_idx), .frame_len(frame_len),
        .payload_addr(pld_addr), .payload_q(pld_dout),
        .err_len(err_len), .err_crc(err_crc), .state(dec_state)
    );

    //-------------------------------------------------------------------------
    // 命令分发 + 多模块寄存器组
    //-------------------------------------------------------------------------
    wire        enc_start;
    wire [7:0]  enc_cmd, enc_mod, enc_idx;
    wire [15:0] enc_len;
    wire        src_req, src_ready;
    wire [8:0]  src_addr;
    wire [7:0]  src_dout;

    module_regfile #(
        .CHK_NUM     (CHK_NUM),
        .ADDR_W      (10),
        .MOD_SYSVAL  (MOD_SYSVAL),
        .MOD_CHKPARAM(MOD_CHKPARAM),
        .SYSVAL_LEN  (51),
        .CHK_LEN     (29),
        .SYSVAL_BASE (0),
        .CHK_BASE    (64),
        .CHK_STRIDE  (32),
        .CMD_WR      (CMD_WR_SYS),
        .CMD_RD      (CMD_RD_SYS),
        .CMD_ACK_WR  (CMD_ACK_WR),
        .CMD_RD_ACK  (CMD_RD_ACK),
        .ACK_ON_WRITE(1)
    ) u_regs (
        .clk(clk), .rst_n(rst_n),
        .frame_valid(frame_valid), .frame_cmd(frame_cmd),
        .frame_mod(frame_mod), .frame_idx(frame_idx), .frame_len(frame_len),
        .pld_addr(pld_addr), .pld_dout(pld_dout),
        .enc_start(enc_start), .enc_cmd(enc_cmd),
        .enc_mod(enc_mod), .enc_idx(enc_idx), .enc_len(enc_len),
        .src_req(src_req), .src_ready(src_ready),
        .src_addr(src_addr), .src_dout(src_dout),
        .app_wr_en(app_wr_en), .app_wr_addr(app_wr_addr), .app_wr_data(app_wr_data),
        .app_rd_addr(app_rd_addr), .app_rd_dout(app_rd_dout),
        .cfg_updated(cfg_updated), .cfg_mod(cfg_mod), .cfg_idx(cfg_idx),
        .cfg_field_we(cfg_field_we), .cfg_field_addr(cfg_field_addr),
        .soft_reset_strobe(soft_reset_strobe)
    );

    //-------------------------------------------------------------------------
    // 帧组包 + TX FIFO + TX 物理层
    //-------------------------------------------------------------------------
    wire       tx_fifo_wr;
    wire [7:0] tx_fifo_din;
    wire       tx_fifo_full;
    wire [7:0] tx_fifo_dout;
    wire       tx_fifo_empty;
    wire       tx_pop;
    wire       uart_tx_ready;

    frame_encoder #(.SOF1(8'hAA), .SOF2(8'h55)) u_enc (
        .clk(clk), .rst_n(rst_n),
        .start(enc_start), .cmd(enc_cmd),
        .mod(enc_mod), .idx(enc_idx), .payload_len(enc_len),
        .src_req(src_req), .src_ready(src_ready),
        .src_addr(src_addr), .src_dout(src_dout),
        .fifo_wr(tx_fifo_wr), .fifo_din(tx_fifo_din), .fifo_full(tx_fifo_full),
        .busy(), .done()
    );

    sync_fifo #(.DW(8), .AW(9)) u_tx_fifo (      // 512 深度, BRAM
        .clk(clk), .rst_n(rst_n),
        .wr_en(tx_fifo_wr), .din(tx_fifo_din),
        .rd_en(tx_pop), .dout(tx_fifo_dout),
        .empty(tx_fifo_empty), .full(tx_fifo_full), .count()
    );

    assign tx_pop = !tx_fifo_empty && uart_tx_ready;

    uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD(BAUD)) u_tx (
        .clk(clk), .rst_n(rst_n),
        .tx_byte(tx_fifo_dout), .tx_valid(tx_pop),
        .tx_ready(uart_tx_ready), .txd(txd)
    );
endmodule
