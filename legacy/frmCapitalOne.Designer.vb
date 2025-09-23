<Global.Microsoft.VisualBasic.CompilerServices.DesignerGenerated()>
Partial Class frmCapitalOne
    Inherits System.Windows.Forms.Form

    'Form overrides dispose to clean up the component list.
    <System.Diagnostics.DebuggerNonUserCode()>
    Protected Overrides Sub Dispose(ByVal disposing As Boolean)
        Try
            If disposing AndAlso components IsNot Nothing Then
                components.Dispose()
            End If
        Finally
            MyBase.Dispose(disposing)
        End Try
    End Sub

    'Required by the Windows Form Designer
    Private components As System.ComponentModel.IContainer

    'NOTE: The following procedure is required by the Windows Form Designer
    'It can be modified using the Windows Form Designer.  
    'Do not modify it using the code editor.
    <System.Diagnostics.DebuggerStepThrough()>
    Private Sub InitializeComponent()
        Dim resources As System.ComponentModel.ComponentResourceManager = New System.ComponentModel.ComponentResourceManager(GetType(frmCapitalOne))
        cmbAPI = New ComboBox()
        txtAccounts = New Label()
        cmdSwitch = New Button()
        cmbAccounts = New ComboBox()
        cmdEpic1Simulate = New Button()
        txtStatus = New TextBox()
        txtHistory = New TextBox()
        txtEpic1Status = New TextBox()
        Label4 = New Label()
        txtSL = New TextBox()
        Label1 = New Label()
        cmbEpic1 = New ComboBox()
        Label2 = New Label()
        txtAccountBalancePerc = New TextBox()
        cmdStart = New Button()
        chkSimTrade = New CheckBox()
        txtAccountDetails = New TextBox()
        txtOrders = New RichTextBox()
        TextBox1 = New TextBox()
        TextBox2 = New TextBox()
        Label3 = New Label()
        Label5 = New Label()
        TextBox3 = New TextBox()
        RichTextBox1 = New RichTextBox()
        PictureBox1 = New PictureBox()
        txtSLThresholds = New TextBox()
        Label6 = New Label()
        txtSLAdjustments = New TextBox()
        Label7 = New Label()
        TextBox4 = New TextBox()
        chkUseTrailingSL = New CheckBox()
        cmdInst = New Button()
        CType(PictureBox1, ComponentModel.ISupportInitialize).BeginInit()
        SuspendLayout()
        ' 
        ' cmbAPI
        ' 
        cmbAPI.BackColor = Color.Black
        cmbAPI.FlatStyle = FlatStyle.Flat
        cmbAPI.Font = New Font("Segoe UI", 9F)
        cmbAPI.ForeColor = Color.Lime
        cmbAPI.FormattingEnabled = True
        cmbAPI.Location = New Point(12, 458)
        cmbAPI.Name = "cmbAPI"
        cmbAPI.Size = New Size(384, 28)
        cmbAPI.TabIndex = 52
        ' 
        ' txtAccounts
        ' 
        txtAccounts.AutoSize = True
        txtAccounts.BackColor = Color.Black
        txtAccounts.Font = New Font("Segoe UI", 9F)
        txtAccounts.ForeColor = Color.Lime
        txtAccounts.Location = New Point(9, 233)
        txtAccounts.Name = "txtAccounts"
        txtAccounts.Size = New Size(86, 20)
        txtAccounts.TabIndex = 51
        txtAccounts.Text = "txtAccounts"
        ' 
        ' cmdSwitch
        ' 
        cmdSwitch.BackColor = Color.Black
        cmdSwitch.Font = New Font("Segoe UI", 9F)
        cmdSwitch.ForeColor = Color.Lime
        cmdSwitch.Location = New Point(302, 491)
        cmdSwitch.Name = "cmdSwitch"
        cmdSwitch.Size = New Size(94, 34)
        cmdSwitch.TabIndex = 50
        cmdSwitch.Text = "Switch Account"
        cmdSwitch.UseVisualStyleBackColor = False
        ' 
        ' cmbAccounts
        ' 
        cmbAccounts.BackColor = Color.Black
        cmbAccounts.FlatStyle = FlatStyle.Flat
        cmbAccounts.Font = New Font("Segoe UI", 9F)
        cmbAccounts.ForeColor = Color.Lime
        cmbAccounts.FormattingEnabled = True
        cmbAccounts.Location = New Point(12, 492)
        cmbAccounts.Name = "cmbAccounts"
        cmbAccounts.Size = New Size(284, 28)
        cmbAccounts.TabIndex = 49
        ' 
        ' cmdEpic1Simulate
        ' 
        cmdEpic1Simulate.BackColor = Color.Black
        cmdEpic1Simulate.Font = New Font("Segoe UI", 9F)
        cmdEpic1Simulate.ForeColor = Color.Lime
        cmdEpic1Simulate.Location = New Point(842, 107)
        cmdEpic1Simulate.Name = "cmdEpic1Simulate"
        cmdEpic1Simulate.Size = New Size(164, 41)
        cmdEpic1Simulate.TabIndex = 42
        cmdEpic1Simulate.Text = "Simulate Close"
        cmdEpic1Simulate.UseVisualStyleBackColor = False
        ' 
        ' txtStatus
        ' 
        txtStatus.BackColor = Color.Black
        txtStatus.BorderStyle = BorderStyle.FixedSingle
        txtStatus.Font = New Font("Segoe UI", 9F)
        txtStatus.ForeColor = Color.Lime
        txtStatus.Location = New Point(410, 564)
        txtStatus.Multiline = True
        txtStatus.Name = "txtStatus"
        txtStatus.ScrollBars = ScrollBars.Vertical
        txtStatus.Size = New Size(597, 274)
        txtStatus.TabIndex = 41
        ' 
        ' txtHistory
        ' 
        txtHistory.BackColor = Color.Black
        txtHistory.BorderStyle = BorderStyle.FixedSingle
        txtHistory.Font = New Font("Segoe UI", 9F)
        txtHistory.ForeColor = Color.Lime
        txtHistory.Location = New Point(410, 258)
        txtHistory.Multiline = True
        txtHistory.Name = "txtHistory"
        txtHistory.ScrollBars = ScrollBars.Vertical
        txtHistory.Size = New Size(596, 267)
        txtHistory.TabIndex = 40
        ' 
        ' txtEpic1Status
        ' 
        txtEpic1Status.BackColor = Color.Black
        txtEpic1Status.BorderStyle = BorderStyle.None
        txtEpic1Status.Font = New Font("Segoe UI", 9F)
        txtEpic1Status.ForeColor = Color.Lime
        txtEpic1Status.Location = New Point(888, 38)
        txtEpic1Status.Name = "txtEpic1Status"
        txtEpic1Status.Size = New Size(118, 20)
        txtEpic1Status.TabIndex = 57
        txtEpic1Status.TextAlign = HorizontalAlignment.Right
        ' 
        ' Label4
        ' 
        Label4.AutoSize = True
        Label4.BackColor = Color.Black
        Label4.Font = New Font("Segoe UI", 9F)
        Label4.ForeColor = Color.Lime
        Label4.Location = New Point(12, 666)
        Label4.Name = "Label4"
        Label4.Size = New Size(75, 20)
        Label4.TabIndex = 64
        Label4.Text = "Stop Loss:"
        ' 
        ' txtSL
        ' 
        txtSL.BackColor = Color.Black
        txtSL.BorderStyle = BorderStyle.FixedSingle
        txtSL.Font = New Font("Segoe UI", 9F)
        txtSL.ForeColor = Color.Lime
        txtSL.Location = New Point(349, 663)
        txtSL.Name = "txtSL"
        txtSL.Size = New Size(47, 27)
        txtSL.TabIndex = 63
        txtSL.TextAlign = HorizontalAlignment.Center
        ' 
        ' Label1
        ' 
        Label1.AutoSize = True
        Label1.BackColor = Color.Black
        Label1.Font = New Font("Segoe UI", 9F)
        Label1.ForeColor = Color.Lime
        Label1.Location = New Point(12, 601)
        Label1.Name = "Label1"
        Label1.Size = New Size(111, 20)
        Label1.TabIndex = 61
        Label1.Text = "Epic 1 to Trade:"
        ' 
        ' cmbEpic1
        ' 
        cmbEpic1.BackColor = Color.Black
        cmbEpic1.FlatStyle = FlatStyle.Flat
        cmbEpic1.Font = New Font("Segoe UI", 9F)
        cmbEpic1.ForeColor = Color.Lime
        cmbEpic1.FormattingEnabled = True
        cmbEpic1.Location = New Point(220, 597)
        cmbEpic1.Name = "cmbEpic1"
        cmbEpic1.Size = New Size(176, 28)
        cmbEpic1.TabIndex = 59
        ' 
        ' Label2
        ' 
        Label2.AutoSize = True
        Label2.BackColor = Color.Black
        Label2.Font = New Font("Segoe UI", 9F)
        Label2.ForeColor = Color.Lime
        Label2.Location = New Point(12, 634)
        Label2.Name = "Label2"
        Label2.Size = New Size(219, 20)
        Label2.TabIndex = 58
        Label2.Text = "Percent (%) of Balance to Trade:"
        ' 
        ' txtAccountBalancePerc
        ' 
        txtAccountBalancePerc.BackColor = Color.Black
        txtAccountBalancePerc.BorderStyle = BorderStyle.FixedSingle
        txtAccountBalancePerc.Font = New Font("Segoe UI", 9F)
        txtAccountBalancePerc.ForeColor = Color.Lime
        txtAccountBalancePerc.Location = New Point(349, 631)
        txtAccountBalancePerc.Name = "txtAccountBalancePerc"
        txtAccountBalancePerc.Size = New Size(47, 27)
        txtAccountBalancePerc.TabIndex = 57
        txtAccountBalancePerc.TextAlign = HorizontalAlignment.Center
        ' 
        ' cmdStart
        ' 
        cmdStart.BackColor = Color.Black
        cmdStart.Font = New Font("Segoe UI", 9F)
        cmdStart.ForeColor = Color.Lime
        cmdStart.Location = New Point(843, 154)
        cmdStart.Name = "cmdStart"
        cmdStart.Size = New Size(164, 70)
        cmdStart.TabIndex = 57
        cmdStart.Text = "Start"
        cmdStart.UseVisualStyleBackColor = False
        ' 
        ' chkSimTrade
        ' 
        chkSimTrade.AutoSize = True
        chkSimTrade.BackColor = Color.Black
        chkSimTrade.Checked = True
        chkSimTrade.CheckState = CheckState.Checked
        chkSimTrade.Font = New Font("Segoe UI", 9F)
        chkSimTrade.ForeColor = Color.Lime
        chkSimTrade.Location = New Point(860, 230)
        chkSimTrade.Name = "chkSimTrade"
        chkSimTrade.Size = New Size(130, 24)
        chkSimTrade.TabIndex = 56
        chkSimTrade.Text = "Simulate Trade"
        chkSimTrade.UseVisualStyleBackColor = False
        ' 
        ' txtAccountDetails
        ' 
        txtAccountDetails.BackColor = Color.Black
        txtAccountDetails.BorderStyle = BorderStyle.FixedSingle
        txtAccountDetails.Font = New Font("Segoe UI", 9F)
        txtAccountDetails.ForeColor = Color.Lime
        txtAccountDetails.Location = New Point(12, 258)
        txtAccountDetails.Multiline = True
        txtAccountDetails.Name = "txtAccountDetails"
        txtAccountDetails.Size = New Size(384, 143)
        txtAccountDetails.TabIndex = 67
        ' 
        ' txtOrders
        ' 
        txtOrders.BackColor = Color.Black
        txtOrders.BorderStyle = BorderStyle.FixedSingle
        txtOrders.Font = New Font("Segoe UI", 9F)
        txtOrders.ForeColor = Color.Lime
        txtOrders.Location = New Point(410, 107)
        txtOrders.Name = "txtOrders"
        txtOrders.ScrollBars = RichTextBoxScrollBars.None
        txtOrders.Size = New Size(427, 143)
        txtOrders.TabIndex = 68
        txtOrders.Text = ""
        ' 
        ' TextBox1
        ' 
        TextBox1.BackColor = Color.FromArgb(CByte(64), CByte(64), CByte(64))
        TextBox1.BorderStyle = BorderStyle.FixedSingle
        TextBox1.Font = New Font("Segoe UI", 9F)
        TextBox1.ForeColor = Color.Lime
        TextBox1.Location = New Point(12, 425)
        TextBox1.Name = "TextBox1"
        TextBox1.Size = New Size(384, 27)
        TextBox1.TabIndex = 69
        TextBox1.Text = "Market Details"
        ' 
        ' TextBox2
        ' 
        TextBox2.BackColor = Color.FromArgb(CByte(64), CByte(64), CByte(64))
        TextBox2.BorderStyle = BorderStyle.FixedSingle
        TextBox2.Font = New Font("Segoe UI", 9F)
        TextBox2.ForeColor = Color.Lime
        TextBox2.Location = New Point(12, 564)
        TextBox2.Name = "TextBox2"
        TextBox2.Size = New Size(384, 27)
        TextBox2.TabIndex = 70
        TextBox2.Text = "Settings"
        ' 
        ' Label3
        ' 
        Label3.AutoSize = True
        Label3.BackColor = Color.Black
        Label3.Font = New Font("Segoe UI", 9F)
        Label3.ForeColor = Color.Lime
        Label3.Location = New Point(920, 9)
        Label3.Name = "Label3"
        Label3.Size = New Size(95, 20)
        Label3.TabIndex = 71
        Label3.Text = "Market Close"
        Label3.TextAlign = ContentAlignment.TopRight
        ' 
        ' Label5
        ' 
        Label5.AutoSize = True
        Label5.BackColor = Color.Black
        Label5.Font = New Font("Segoe UI", 9F)
        Label5.ForeColor = Color.Lime
        Label5.Location = New Point(410, 84)
        Label5.Name = "Label5"
        Label5.Size = New Size(86, 20)
        Label5.TabIndex = 72
        Label5.Text = "Open Trade"
        ' 
        ' TextBox3
        ' 
        TextBox3.BackColor = Color.FromArgb(CByte(64), CByte(64), CByte(64))
        TextBox3.BorderStyle = BorderStyle.FixedSingle
        TextBox3.Font = New Font("Segoe UI", 9F)
        TextBox3.ForeColor = Color.Lime
        TextBox3.Location = New Point(410, 531)
        TextBox3.Name = "TextBox3"
        TextBox3.Size = New Size(597, 27)
        TextBox3.TabIndex = 73
        TextBox3.Text = "Logs"
        ' 
        ' RichTextBox1
        ' 
        RichTextBox1.BackColor = Color.Black
        RichTextBox1.BorderStyle = BorderStyle.None
        RichTextBox1.Font = New Font("Ravie", 25.8F, FontStyle.Regular, GraphicsUnit.Point, CByte(0))
        RichTextBox1.ForeColor = Color.Lime
        RichTextBox1.Location = New Point(410, 1)
        RichTextBox1.Name = "RichTextBox1"
        RichTextBox1.Size = New Size(486, 78)
        RichTextBox1.TabIndex = 74
        RichTextBox1.Text = "Capital One V1.0"
        ' 
        ' PictureBox1
        ' 
        PictureBox1.BackgroundImageLayout = ImageLayout.None
        PictureBox1.Image = CType(resources.GetObject("PictureBox1.Image"), Image)
        PictureBox1.Location = New Point(-2, -3)
        PictureBox1.Name = "PictureBox1"
        PictureBox1.Size = New Size(398, 257)
        PictureBox1.SizeMode = PictureBoxSizeMode.StretchImage
        PictureBox1.TabIndex = 75
        PictureBox1.TabStop = False
        ' 
        ' txtSLThresholds
        ' 
        txtSLThresholds.BackColor = Color.Black
        txtSLThresholds.BorderStyle = BorderStyle.FixedSingle
        txtSLThresholds.Font = New Font("Segoe UI", 9F)
        txtSLThresholds.ForeColor = Color.Lime
        txtSLThresholds.Location = New Point(252, 760)
        txtSLThresholds.Name = "txtSLThresholds"
        txtSLThresholds.Size = New Size(144, 27)
        txtSLThresholds.TabIndex = 76
        txtSLThresholds.TextAlign = HorizontalAlignment.Center
        ' 
        ' Label6
        ' 
        Label6.AutoSize = True
        Label6.BackColor = Color.Black
        Label6.Font = New Font("Segoe UI", 9F)
        Label6.ForeColor = Color.Lime
        Label6.Location = New Point(12, 763)
        Label6.Name = "Label6"
        Label6.Size = New Size(220, 20)
        Label6.TabIndex = 77
        Label6.Text = "Stop Loss Thresholds (commas):"
        ' 
        ' txtSLAdjustments
        ' 
        txtSLAdjustments.BackColor = Color.Black
        txtSLAdjustments.BorderStyle = BorderStyle.FixedSingle
        txtSLAdjustments.Font = New Font("Segoe UI", 9F)
        txtSLAdjustments.ForeColor = Color.Lime
        txtSLAdjustments.Location = New Point(252, 791)
        txtSLAdjustments.Name = "txtSLAdjustments"
        txtSLAdjustments.Size = New Size(144, 27)
        txtSLAdjustments.TabIndex = 78
        txtSLAdjustments.TextAlign = HorizontalAlignment.Center
        ' 
        ' Label7
        ' 
        Label7.AutoSize = True
        Label7.BackColor = Color.Black
        Label7.Font = New Font("Segoe UI", 9F)
        Label7.ForeColor = Color.Lime
        Label7.Location = New Point(12, 794)
        Label7.Name = "Label7"
        Label7.Size = New Size(231, 20)
        Label7.TabIndex = 79
        Label7.Text = "Stop Loss Adjustments (commas):"
        ' 
        ' TextBox4
        ' 
        TextBox4.BackColor = Color.FromArgb(CByte(64), CByte(64), CByte(64))
        TextBox4.BorderStyle = BorderStyle.FixedSingle
        TextBox4.Font = New Font("Segoe UI", 9F)
        TextBox4.ForeColor = Color.Lime
        TextBox4.Location = New Point(12, 696)
        TextBox4.Name = "TextBox4"
        TextBox4.Size = New Size(384, 27)
        TextBox4.TabIndex = 80
        TextBox4.Text = "Trailing Stop Loss"
        ' 
        ' chkUseTrailingSL
        ' 
        chkUseTrailingSL.AutoSize = True
        chkUseTrailingSL.BackColor = Color.Black
        chkUseTrailingSL.CheckAlign = ContentAlignment.MiddleRight
        chkUseTrailingSL.Checked = True
        chkUseTrailingSL.CheckState = CheckState.Checked
        chkUseTrailingSL.Font = New Font("Segoe UI", 9F)
        chkUseTrailingSL.ForeColor = Color.Lime
        chkUseTrailingSL.Location = New Point(12, 732)
        chkUseTrailingSL.Name = "chkUseTrailingSL"
        chkUseTrailingSL.Size = New Size(196, 24)
        chkUseTrailingSL.TabIndex = 81
        chkUseTrailingSL.Text = "Use Trailing Stop Losses?"
        chkUseTrailingSL.UseVisualStyleBackColor = False
        ' 
        ' cmdInst
        ' 
        cmdInst.Location = New Point(660, 63)
        cmdInst.Name = "cmdInst"
        cmdInst.Size = New Size(94, 29)
        cmdInst.TabIndex = 82
        cmdInst.Text = "Button1"
        cmdInst.UseVisualStyleBackColor = True
        ' 
        ' frmCapitalOne
        ' 
        AutoScaleDimensions = New SizeF(8F, 20F)
        AutoScaleMode = AutoScaleMode.Font
        BackColor = Color.Black
        ClientSize = New Size(1018, 852)
        Controls.Add(cmdInst)
        Controls.Add(chkUseTrailingSL)
        Controls.Add(TextBox4)
        Controls.Add(txtSLAdjustments)
        Controls.Add(Label7)
        Controls.Add(txtSLThresholds)
        Controls.Add(Label6)
        Controls.Add(RichTextBox1)
        Controls.Add(TextBox3)
        Controls.Add(Label5)
        Controls.Add(Label3)
        Controls.Add(TextBox2)
        Controls.Add(TextBox1)
        Controls.Add(txtSL)
        Controls.Add(Label4)
        Controls.Add(chkSimTrade)
        Controls.Add(cmdStart)
        Controls.Add(txtAccountBalancePerc)
        Controls.Add(Label2)
        Controls.Add(cmbEpic1)
        Controls.Add(Label1)
        Controls.Add(txtOrders)
        Controls.Add(txtAccountDetails)
        Controls.Add(txtEpic1Status)
        Controls.Add(cmbAPI)
        Controls.Add(txtAccounts)
        Controls.Add(cmdSwitch)
        Controls.Add(cmbAccounts)
        Controls.Add(cmdEpic1Simulate)
        Controls.Add(txtStatus)
        Controls.Add(txtHistory)
        Controls.Add(PictureBox1)
        ForeColor = Color.Lime
        Name = "frmCapitalOne"
        StartPosition = FormStartPosition.CenterScreen
        Text = "Capital One"
        CType(PictureBox1, ComponentModel.ISupportInitialize).EndInit()
        ResumeLayout(False)
        PerformLayout()
    End Sub
    Friend WithEvents cmbAPI As ComboBox
    Friend WithEvents txtAccounts As Label
    Friend WithEvents cmdSwitch As Button
    Friend WithEvents cmbAccounts As ComboBox
    Friend WithEvents cmdEpic1Simulate As Button
    Friend WithEvents txtStatus As TextBox
    Friend WithEvents txtHistory As TextBox
    Friend WithEvents txtEpic1Status As TextBox
    Friend WithEvents cmbEpic1 As ComboBox
    Friend WithEvents Label2 As Label
    Friend WithEvents txtAccountBalancePerc As TextBox
    Friend WithEvents chkSimTrade As CheckBox
    Friend WithEvents Label1 As Label
    Friend WithEvents cmdStart As Button
    Friend WithEvents Label4 As Label
    Friend WithEvents txtSL As TextBox
    Friend WithEvents txtAccountDetails As TextBox
    Friend WithEvents txtOrders As RichTextBox
    Friend WithEvents TextBox1 As TextBox
    Friend WithEvents TextBox2 As TextBox
    Friend WithEvents Label3 As Label
    Friend WithEvents Label5 As Label
    Friend WithEvents TextBox3 As TextBox
    Friend WithEvents RichTextBox1 As RichTextBox
    Friend WithEvents PictureBox1 As PictureBox
    Friend WithEvents txtSLThresholds As TextBox
    Friend WithEvents Label6 As Label
    Friend WithEvents txtSLAdjustments As TextBox
    Friend WithEvents Label7 As Label
    Friend WithEvents TextBox4 As TextBox
    Friend WithEvents chkUseTrailingSL As CheckBox
    Friend WithEvents cmdInst As Button
    'Friend WithEvents cmdEpic1Simulate As System.Windows.Forms.Button
    'Friend WithEvents cmdEpic2Simulate As System.Windows.Forms.Button

End Class
