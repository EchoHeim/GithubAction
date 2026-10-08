//==============================================================================
// tb_uart_protocol.v -- 串口协议引擎系统级 testbench v1.1（端到端位级回环）
//------------------------------------------------------------------------------
// 用例:
//   T1  WR SystemValue(51B) -> app 总线读回比对
//       (含 FP-owned 偏移不被覆盖 + payload 内嵌 0xAA55 假帧头)
//   T2  写应答 ACK 帧格式+CRC 比对
//   T3  RD SystemValue -> 60 字节应答帧头/payload/CRC 全比对
//   T4  WR CheckParam ch3(29B) -> 按地址 160 读回比对 (多模块多通道)
//   T5  RD CheckParam ch3 -> 38 字节应答帧全比对
//   T6  CRC 坏帧 -> err_crc, 寄存器组不更新
//   T7  超长帧(len=600) -> err_len
//   T8  非法模块(MOD=0x77) -> ACK status=0x03
//   T9  长度不符(WR SystemValue 传 30B) -> ACK status=0x01
// 运行(iverilog):
//   iverilog -g2001 -o sim.vvp rtl/*.v sim/tb_uart_protocol.v && vvp sim.vvp
//==============================================================================
`timescale 1ns/1ps
module tb_uart_protocol;
    localparam integer CLK_FREQ = 50_000_000;
    localparam integer BAUD     = 115200;
    localparam integer BIT_NS   = (CLK_FREQ / BAUD) * 20;   // 8680ns

    // 模块表(与 RTL 参数保持一致)
    localparam [7:0]  MOD_SYSVAL   = 8'h01;
    localparam [7:0]  MOD_CHKPARAM = 8'h02;
    localparam [9:0]  CHK_BASE     = 10'd64;
    localparam [9:0]  CHK_STRIDE   = 10'd32;
    localparam [9:0]  CHK3_ADDR    = CHK_BASE + 10'd3 * CHK_STRIDE;   // 160

    reg  clk = 0;
    reg  rst_n = 0;
    reg  rxd = 1;
    wire txd;

    reg        app_wr_en = 0;
    reg  [9:0] app_wr_addr = 0;
    reg  [7:0] app_wr_data = 0;
    reg  [9:0] app_rd_addr = 0;
    wire [7:0] app_rd_dout;
    wire       cfg_updated, cfg_field_we, soft_reset_strobe, err_crc, err_len;
    wire [7:0] cfg_mod, cfg_idx;
    wire [9:0] cfg_field_addr;
    wire [3:0] dec_state;

    uart_protocol_top #(
        .CLK_FREQ(CLK_FREQ), .BAUD(BAUD), .CHK_NUM(20)
    ) dut (
        .clk(clk), .rst_n(rst_n), .rxd(rxd), .txd(txd),
        .app_wr_en(app_wr_en), .app_wr_addr(app_wr_addr), .app_wr_data(app_wr_data),
        .app_rd_addr(app_rd_addr), .app_rd_dout(app_rd_dout),
        .cfg_updated(cfg_updated), .cfg_mod(cfg_mod), .cfg_idx(cfg_idx),
        .cfg_field_we(cfg_field_we), .cfg_field_addr(cfg_field_addr),
        .soft_reset_strobe(soft_reset_strobe),
        .err_crc(err_crc), .err_len(err_len), .dec_state(dec_state)
    );

    always #10 clk = ~clk;    // 50MHz

    //-------------------------------------------------------------------------
    // 事件锁存(脉冲展宽, 防止 wait 错过)
    //-------------------------------------------------------------------------
    integer upd_cnt = 0;
    reg err_crc_seen = 0, err_len_seen = 0, rst_strobe_seen = 0;
    always @(posedge clk) begin
        if (cfg_updated)        upd_cnt         = upd_cnt + 1;
        if (err_crc)            err_crc_seen    = 1;
        if (err_len)            err_len_seen    = 1;
        if (soft_reset_strobe)  rst_strobe_seen = 1;
    end

    //-------------------------------------------------------------------------
    // 发送字节流抓取(encoder -> tx_fifo 写口)
    //-------------------------------------------------------------------------
    integer tx_cnt = 0;
    reg [7:0] tx_stream [0:1023];
    always @(posedge clk) begin
        if (dut.tx_fifo_wr) begin
            tx_stream[tx_cnt] <= dut.tx_fifo_din;
            tx_cnt            <= tx_cnt + 1;
        end
    end

    //-------------------------------------------------------------------------
    // CRC16-MODBUS(与 RTL 等价)
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

    integer errors = 0;
    integer i;
    integer n;
    reg [7:0] expected     [0:63];   // SystemValue 模型
    reg [7:0] expected_chk [0:63];   // CheckParam 模型
    reg [7:0] owned_off    [0:15];   // SystemValue 中 FPGA-owned 的字节偏移
    integer   OWNED_N = 14;
    reg [15:0] exp_crc;
    reg [9:0] a;

    //-------------------------------------------------------------------------
    // 激励任务
    //-------------------------------------------------------------------------
    task uart_send_byte(input [7:0] d);
        integer i;
        begin
            rxd = 1'b0; #(BIT_NS);
            for (i = 0; i < 8; i = i + 1) begin
                rxd = d[i]; #(BIT_NS);
            end
            rxd = 1'b1; #(BIT_NS);
        end
    endtask

    reg [7:0] frame_mem [0:511];

    task send_frame(input [7:0] cmd, input [7:0] mod, input [7:0] idx,
                    input integer len, input bad);
        reg [15:0] crc;
        integer i;
        begin
            crc = 16'hFFFF;
            crc = crc16_byte(crc, cmd);
            crc = crc16_byte(crc, mod);
            crc = crc16_byte(crc, idx);
            crc = crc16_byte(crc, len[7:0]);
            crc = crc16_byte(crc, len[15:8]);
            for (i = 0; i < len; i = i + 1)
                crc = crc16_byte(crc, frame_mem[i]);
            if (bad) crc = crc ^ 16'hBEEF;
            uart_send_byte(8'hAA); uart_send_byte(8'h55);
            uart_send_byte(cmd); uart_send_byte(mod); uart_send_byte(idx);
            uart_send_byte(len[7:0]); uart_send_byte(len[15:8]);
            for (i = 0; i < len; i = i + 1)
                uart_send_byte(frame_mem[i]);
            uart_send_byte(crc[7:0]); uart_send_byte(crc[15:8]);
        end
    endtask

    // 计算一帧应答的期望 CRC(供 ACK/读应答比对)
    function [15:0] crc_of(input [7:0] cmd, input [7:0] mod, input [7:0] idx,
                           input integer len, input src_sel);
        reg [15:0] c;
        integer i;
        begin
            c = 16'hFFFF;
            c = crc16_byte(c, cmd);
            c = crc16_byte(c, mod);
            c = crc16_byte(c, idx);
            c = crc16_byte(c, len[7:0]);
            c = crc16_byte(c, len[15:8]);
            if (!src_sel) begin     // src_sel=0: 从 expected[] 取 payload
                for (i = 0; i < len; i = i + 1)
                    c = crc16_byte(c, expected[i]);
            end else begin          // src_sel=1: 从 expected_chk[] 取 payload
                for (i = 0; i < len; i = i + 1)
                    c = crc16_byte(c, expected_chk[i]);
            end
            crc_of = c;
        end
    endfunction

    task app_write(input [9:0] addr, input [7:0] data);
        begin
            @(posedge clk);
            app_wr_en   <= 1'b1;
            app_wr_addr <= addr;
            app_wr_data <= data;
            @(posedge clk);
            app_wr_en   <= 1'b0;
        end
    endtask

    task check(input [7:0] got, input [7:0] exp, input [127:0] tag);
        begin
            if (got !== exp) begin
                $display("FAIL [%0s]: got=%02h exp=%02h  @%0t", tag, got, exp, $time);
                errors = errors + 1;
            end
        end
    endtask

    //-------------------------------------------------------------------------
    // 主流程
    //-------------------------------------------------------------------------
    initial begin
        rst_n = 0; #200;
        rst_n = 1; #1000;

        //=== T1: WR SystemValue 整帧写入 ======================================
        // FPGA-owned 偏移表(必须与 RTL 的 is_fpga_owned 一致):
        //   0x09 CurPressure / 0x0B TempPressure / 0x23-0x24 TempRunSpeed
        //   0x29-0x2A RotationSpeed_MotorVal / 0x2B-0x2C CurErrNumber
        //   0x2D-0x2E CurRejectedNum / 0x2F-0x32 CurCheckNumber
        owned_off[0]  = 8'h09;  owned_off[1]  = 8'h0B;
        owned_off[2]  = 8'h23;  owned_off[3]  = 8'h24;
        owned_off[4]  = 8'h29;  owned_off[5]  = 8'h2A;
        owned_off[6]  = 8'h2B;  owned_off[7]  = 8'h2C;
        owned_off[8]  = 8'h2D;  owned_off[9]  = 8'h2E;
        owned_off[10] = 8'h2F;  owned_off[11] = 8'h30;
        owned_off[12] = 8'h31;  owned_off[13] = 8'h32;

        // 预写 owned 偏移(模拟业务动态量), 值 0xB0+n, 应保持不被 ARM 帧覆盖
        for (n = 0; n < OWNED_N; n = n + 1)
            app_write({2'b00, owned_off[n]}, 8'hB0 + n[7:0]);

        for (i = 0; i < 51; i = i + 1)
            frame_mem[i] = $random;
        // owned 偏移填 0xEE(不应生效)
        for (n = 0; n < OWNED_N; n = n + 1)
            frame_mem[owned_off[n]] = 8'hEE;
        // 假帧头测试: payload 里嵌 AA 55
        frame_mem[8'h03] = 8'hAA; frame_mem[8'h04] = 8'h55;
        frame_mem[8'h15] = 8'hAA; frame_mem[8'h16] = 8'h55;
        frame_mem[8'h05] = 8'h01;    // SoftReset, 验证 strobe

        for (i = 0; i < 51; i = i + 1)
            expected[i] = frame_mem[i];
        for (n = 0; n < OWNED_N; n = n + 1)
            expected[owned_off[n]] = 8'hB0 + n[7:0];

        upd_cnt = 0;  tx_cnt = 0;
        send_frame(8'h01, MOD_SYSVAL, 8'h00, 51, 1'b0);
        #50_000;
        if (upd_cnt != 1) begin
            $display("FAIL: WR_SYS not applied, upd_cnt=%0d", upd_cnt);
            errors = errors + 1;
        end
        if (cfg_mod !== MOD_SYSVAL || cfg_idx !== 8'h00) begin
            $display("FAIL: cfg_mod/idx wrong: %02h/%02h", cfg_mod, cfg_idx);
            errors = errors + 1;
        end
        for (i = 0; i < 51; i = i + 1) begin
            app_rd_addr = i[9:0]; #1;
            check(app_rd_dout, expected[i], "T1 rdback");
        end
        if (!rst_strobe_seen) begin
            $display("FAIL: SoftReset strobe missing");
            errors = errors + 1;
        end
        $display("T1 WR SystemValue rdback done (errors=%0d)", errors);

        //=== T2: 写应答 ACK 帧 (7 头 + 1 + 2 = 10B) ==========================
        #50_000;
        if (tx_cnt != 10) begin
            $display("FAIL: ACK len=%0d (exp 10)", tx_cnt);
            errors = errors + 1;
        end
        check(tx_stream[0], 8'hAA, "ACK sof1");
        check(tx_stream[1], 8'h55, "ACK sof2");
        check(tx_stream[2], 8'h81, "ACK cmd");
        check(tx_stream[3], MOD_SYSVAL, "ACK mod");
        check(tx_stream[4], 8'h00, "ACK idx");
        check(tx_stream[5], 8'h01, "ACK len_l");
        check(tx_stream[6], 8'h00, "ACK len_h");
        check(tx_stream[7], 8'h00, "ACK status");
        exp_crc = crc16_byte(16'hFFFF, 8'h81);
        exp_crc = crc16_byte(exp_crc, MOD_SYSVAL);
        exp_crc = crc16_byte(exp_crc, 8'h00);
        exp_crc = crc16_byte(exp_crc, 8'h01);
        exp_crc = crc16_byte(exp_crc, 8'h00);
        exp_crc = crc16_byte(exp_crc, 8'h00);
        check(tx_stream[8],  exp_crc[7:0],  "ACK crc_l");
        check(tx_stream[9],  exp_crc[15:8], "ACK crc_h");
        $display("T2 ACK frame done (errors=%0d)", errors);

        //=== T3: RD SystemValue -> 60 字节应答 ================================
        tx_cnt = 0;
        send_frame(8'h02, MOD_SYSVAL, 8'h00, 0, 1'b0);
        #600_000;
        if (tx_cnt != 60) begin
            $display("FAIL: RD_ACK len=%0d (exp 60)", tx_cnt);
            errors = errors + 1;
        end
        check(tx_stream[0], 8'hAA, "SACK sof1");
        check(tx_stream[1], 8'h55, "SACK sof2");
        check(tx_stream[2], 8'h82, "SACK cmd");
        check(tx_stream[3], MOD_SYSVAL, "SACK mod");
        check(tx_stream[4], 8'h00, "SACK idx");
        check(tx_stream[5], 8'h33, "SACK len_l");
        check(tx_stream[6], 8'h00, "SACK len_h");
        for (i = 0; i < 51; i = i + 1)
            check(tx_stream[7+i], expected[i], "SACK payload");
        exp_crc = crc_of(8'h82, MOD_SYSVAL, 8'h00, 51, 1'b0);
        check(tx_stream[58], exp_crc[7:0],  "SACK crc_l");
        check(tx_stream[59], exp_crc[15:8], "SACK crc_h");
        $display("T3 RD SystemValue loopback done (errors=%0d)", errors);

        //=== T4: WR CheckParam 通道3 (29B) ====================================
        for (i = 0; i < 29; i = i + 1)
            frame_mem[i] = $random;
        frame_mem[8'h02] = 8'hEE;               // CheckType (FP-owned, 应保持)
        for (i = 0; i < 29; i = i + 1)
            expected_chk[i] = frame_mem[i];
        expected_chk[8'h02] = 8'hF1;            // 业务侧预写: GJC-800 型号

        // 业务侧预写 CheckType 模拟 FPGA 硬件自识别结果
        app_write(CHK3_ADDR + 10'h02, 8'hF1);

        upd_cnt = 0;
        send_frame(8'h01, MOD_CHKPARAM, 8'd3, 29, 1'b0);
        #50_000;
        if (upd_cnt != 1) begin
            $display("FAIL: WR CheckParam not applied, upd_cnt=%0d", upd_cnt);
            errors = errors + 1;
        end
        if (cfg_mod !== MOD_CHKPARAM || cfg_idx !== 8'd3) begin
            $display("FAIL: CheckParam cfg_mod/idx = %02h/%0d", cfg_mod, cfg_idx);
            errors = errors + 1;
        end
        for (i = 0; i < 29; i = i + 1) begin
            a = CHK3_ADDR + i[9:0];
            app_rd_addr = a; #1;
            check(app_rd_dout, expected_chk[i], "T4 ch3 rdback");
        end
        // 通道隔离: 通道 0 与通道 4 不应被写入影响
        app_rd_addr = CHK_BASE; #1;
        check(app_rd_dout, 8'h00, "T4 ch0 untouched");
        app_rd_addr = CHK_BASE + 10'd4 * CHK_STRIDE; #1;
        check(app_rd_dout, 8'h00, "T4 ch4 untouched");
        $display("T4 WR CheckParam ch3 rdback done (errors=%0d)", errors);

        //=== T5: RD CheckParam 通道3 -> 38 字节应答 ===========================
        tx_cnt = 0;
        send_frame(8'h02, MOD_CHKPARAM, 8'd3, 0, 1'b0);
        #600_000;
        if (tx_cnt != 38) begin
            $display("FAIL: CHK RD_ACK len=%0d (exp 38)", tx_cnt);
            errors = errors + 1;
        end
        check(tx_stream[0], 8'hAA, "CACK sof1");
        check(tx_stream[1], 8'h55, "CACK sof2");
        check(tx_stream[2], 8'h82, "CACK cmd");
        check(tx_stream[3], MOD_CHKPARAM, "CACK mod");
        check(tx_stream[4], 8'd3, "CACK idx");
        check(tx_stream[5], 8'h1D, "CACK len_l");
        check(tx_stream[6], 8'h00, "CACK len_h");
        for (i = 0; i < 29; i = i + 1)
            check(tx_stream[7+i], expected_chk[i], "CACK payload");
        exp_crc = crc_of(8'h82, MOD_CHKPARAM, 8'd3, 29, 1'b1);
        check(tx_stream[36], exp_crc[7:0],  "CACK crc_l");
        check(tx_stream[37], exp_crc[15:8], "CACK crc_h");
        $display("T5 RD CheckParam ch3 loopback done (errors=%0d)", errors);

        //=== T6: CRC 坏帧 ======================================================
        err_crc_seen = 0;
        for (i = 0; i < 51; i = i + 1)
            frame_mem[i] = $random;
        send_frame(8'h01, MOD_SYSVAL, 8'h00, 51, 1'b1);
        #50_000;
        if (!err_crc_seen) begin
            $display("FAIL: no err_crc on bad frame");
            errors = errors + 1;
        end
        if (upd_cnt != 1) begin
            $display("FAIL: bad frame applied to regs!");
            errors = errors + 1;
        end
        $display("T6 bad-CRC frame rejected (errors=%0d)", errors);

        //=== T7: 超长帧 ========================================================
        err_len_seen = 0;
        uart_send_byte(8'hAA); uart_send_byte(8'h55);
        uart_send_byte(8'h01); uart_send_byte(8'h01); uart_send_byte(8'h00);
        uart_send_byte(8'h58); uart_send_byte(8'h02);   // len=600
        #50_000;
        if (!err_len_seen) begin
            $display("FAIL: no err_len on oversized frame");
            errors = errors + 1;
        end
        $display("T7 oversized frame rejected (errors=%0d)", errors);

        //=== T8: 非法模块 -> ACK status=0x03 ==================================
        tx_cnt = 0;
        send_frame(8'h02, 8'h77, 8'h00, 0, 1'b0);      // 模块 0x77 未定义
        #100_000;
        if (tx_cnt != 10) begin
            $display("FAIL: invalid-mod ACK len=%0d (exp 10)", tx_cnt);
            errors = errors + 1;
        end
        check(tx_stream[2], 8'h81, "IM ACK cmd");
        check(tx_stream[3], 8'h77, "IM ACK mod echo");
        check(tx_stream[7], 8'h03, "IM ACK status");
        $display("T8 invalid module rejected with status=3 (errors=%0d)", errors);

        //=== T9: 长度不符 -> ACK status=0x01 ==================================
        tx_cnt = 0;
        for (i = 0; i < 30; i = i + 1)
            frame_mem[i] = $random;
        send_frame(8'h01, MOD_SYSVAL, 8'h00, 30, 1'b0);  // SystemValue 应为 51B
        #100_000;
        if (tx_cnt != 10) begin
            $display("FAIL: len-err ACK len=%0d (exp 10)", tx_cnt);
            errors = errors + 1;
        end
        check(tx_stream[3], MOD_SYSVAL, "LE ACK mod echo");
        check(tx_stream[7], 8'h01, "LE ACK status");
        $display("T9 wrong length rejected with status=1 (errors=%0d)", errors);

        //=== 汇总 ==============================================================
        if (errors == 0)
            $display("=== ALL TESTS PASSED ===");
        else
            $display("=== %0d ERRORS ===", errors);
        $finish;
    end

    initial begin
        #200_000_000;   // 全局看门狗 200ms
        $display("FAIL: global timeout");
        $finish;
    end
endmodule
