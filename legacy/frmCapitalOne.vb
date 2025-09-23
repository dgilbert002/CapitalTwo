Imports System.Net.Http
Imports System.Text
Imports Newtonsoft.Json.Linq
Imports System.Globalization
Imports System.Threading
Imports Newtonsoft.Json
Imports System.Windows.Forms.VisualStyles.VisualStyleElement.TrackBar

Public Class frmCapitalOne

    Private BotisRunning As Boolean = False
    Private WithEvents epic1Timer As System.Windows.Forms.Timer
    Private WithEvents generalTimer As System.Windows.Forms.Timer ' Add General Timer
    Private generalTimerCounter As Integer = 0
    Private epic1TradeFlag As Boolean = False
    Private apiHelper As ApiHelper
    Private epic1ClosingTime As DateTime
    Private epic1DealId As String
    Private epic1TradeOpened As Boolean = False
    Private epic1TradeClosed As Boolean = False
    Private epic1ClosingTradeInProgress As Boolean = False
    Private epic1TradeOpenedInProgress As Boolean = False
    Private NumberOfEpicsLoaded As Integer = 0
    Private syncCounter As Integer = 0
    Private syncMode As Boolean = False

    Private Epic1InClosingMode As Boolean = False
    Private Epic1CloseAttempts As Integer = 0

    ' Declare highestThresholdActedUpon at the class level to track the highest threshold acted upon
    Private highestThresholdActedUpon As Decimal = 0D


    ' File path for logging WebSocket responses
    Public Shared ReadOnly LOG_FILE_PATH As String = System.IO.Path.Combine(System.AppDomain.CurrentDomain.BaseDirectory, "CapitalOne_Log.txt")

    Private Async Sub MyMill_Load(sender As Object, e As EventArgs) Handles MyBase.Load
        BotisRunning = False
        ClearLogFile()

        ' Predefined list of EPICs
        Dim epicList As List(Of String) = New List(Of String) From {"SOXL", "SPXL", "SPXS", "GOOG", "TECL", "MSTR", "COIN", "TNA", "NVDA", "MARA", "BTCUSD", "XRPUSD", "ETHUSD", "DOGEUSD", "XLMUSD", "ADAUSD", "SOLUSD", "DOTUSD", "SHIBUSD", "BCHUSD", "BTCEUR", "XRPEUR", "PEPEUSD", "UNIUSD", "LTCUSD", "ETHEUR", "AVAXUSD", "BONKUSD", "CQTUSD", "FLOKIUSD", "LUNA2USD", "C10X", "XLMBTC", "ALGOUSD", "GALAUSD", "SUIUSD", "MATICUSD", "LINKUSD", "LUNCUSD", "SANDUSD", "SRMUSD", "BNBUSD", "ATOMUSD", "FILUSD", "FETUSD", "ADABTC", "XRPBTC", "TRXUSD", "ETHBTC", "NEARUSD", "MIRUSD", "JASMYUSD", "MANAUSD", "TURBOUSD", "FTMUSD", "MEWUSD", "ARBUSD", "KSMUSD", "ICPUSD", "JUNOUSD", "APEUSD", "BSXUSD", "ENJUSD", "WIFUSD", "GRTUSD", "SEIUSD", "RENDERUSD", "SCRTUSD", "INJUSD", "TONUSD", "MEMEUSD", "ONDOUSD", "OMGUSD", "BODENUSD", "AAVEUSD", "OXTUSD", "TIAUSD", "TREMPUSD", "EOSUSD", "0XUSD", "ACAUSD", "UNFIUSD", "SBRUSD", "SUSHIUSD", "LTCEUR", "POPCATUSD", "STXUSD", "ETCUSD", "XTZUSD", "APTUSD", "KINTUSD", "LTCBTC", "ALPHAUSD", "TAOUSD", "QTUMUSD", "MCUSD", "LCXUSD", "GARIUSD", "USDTUSD", "IMXUSD", "CHZUSD", "REPUSD", "BCHBTC", "CRVUSD", "OXYUSD"}

        ' Populate the combo boxes
        cmbEpic1.Items.AddRange(epicList.ToArray())

        ' Load last saved or default values for cmbEpic1 
        cmbEpic1.SelectedItem = If(String.IsNullOrEmpty(My.Settings.Epic1), "TECL", My.Settings.Epic1)
        ' Load the saved Account Balance Percentage or default value
        txtAccountBalancePerc.Text = If(String.IsNullOrEmpty(My.Settings.AccountBalancePerc), "99", My.Settings.AccountBalancePerc)
        txtSL.Text = My.Settings.StopLoss.ToString()
        txtSLThresholds.Text = My.Settings.SLThresholds
        txtSLAdjustments.Text = My.Settings.SLAdjustments

        ' Populate cmbAPI with options
        cmbAPI.Items.Clear()
        cmbAPI.Items.Add(New KeyValuePair(Of String, String)("Demo", "https://demo-api-capital.backend-capital.com/api/v1"))
        cmbAPI.Items.Add(New KeyValuePair(Of String, String)("Live", "https://api-capital.backend-capital.com/api/v1"))

        ' Set default selection (e.g., Demo)
        cmbAPI.SelectedIndex = 0

        ' Initialize session and fetch accounts
        Await InitializeAndFetchAccountsAsync()

        Await FetchAndStoreDealIdsAsync()

        ' Start general timer
        generalTimer = New System.Windows.Forms.Timer()
        AddHandler generalTimer.Tick, AddressOf OnGeneralTimerTick
        generalTimer.Interval = 5000 ' Set interval to 1 second
        generalTimer.Start()

        ' Init Epic Timers
        InitializeTimers()
    End Sub

    Private Async Function InitializeAndFetchAccountsAsync() As Task
        Try
            ' Initialize the ApiHelper with the API key and pass the current form instance (Me)
            apiHelper = New ApiHelper(GlobalVariables.API_KEY, Me)

            ' Set the BASE_URL from the selected API in the combo box
            Dim selectedApi As KeyValuePair(Of String, String) = CType(cmbAPI.SelectedItem, KeyValuePair(Of String, String))
            GlobalVariables.BASE_URL = selectedApi.Value
            GlobalVariables.UpdateUrls()

            ' Establish a session and retrieve tokens
            Await apiHelper.GetSessionAsync(GlobalVariables.BASE_URL & "/session", GlobalVariables.IDENTIFIER, GlobalVariables.PASSWORD)

            ' Fetch and populate the accounts in the combo box
            Await FetchAndPopulateAccountsAsync()

            ' Set GlobalVariables.ACCOUNT_ID to the first account or active account
            If cmbAccounts.SelectedItem IsNot Nothing Then
                Dim selectedAccount As KeyValuePair(Of String, String) = CType(cmbAccounts.SelectedItem, KeyValuePair(Of String, String))
                GlobalVariables.ACCOUNT_ID = selectedAccount.Key
            End If

        Catch ex As HttpRequestException
            Debug.Print($"Error fetching accounts: {ex.Message}")
        Catch ex As Exception
            MessageBox.Show($"Unexpected error: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Function

    Private Async Function FetchAndPopulateAccountsAsync() As Task
        Try
            ' Fetch account details
            Dim accountDetailsJson As String = Await apiHelper.FetchAccountDetailsAsync()

            If Not String.IsNullOrEmpty(accountDetailsJson) Then
                Dim accountDetails As JObject = JObject.Parse(accountDetailsJson)
                cmbAccounts.Items.Clear()

                For Each account As JObject In accountDetails("accounts")
                    Dim accountId As String = account("accountId").ToString()
                    Dim accountName As String = account("accountName").ToString()

                    ' Display format: "AccountName (AccountID)"
                    Dim displayText As String = $"{accountName} ({accountId})"

                    ' Add to the combo box as a KeyValuePair
                    cmbAccounts.Items.Add(New KeyValuePair(Of String, String)(accountId, displayText))
                Next

                ' Optionally, set the selected item in the combo box to the active account
                Dim activeAccountId As String = accountDetails("accounts")(0)("accountId").ToString()
                Dim activeAccountName As String = accountDetails("accounts")(0)("accountName").ToString()

                ' Update the ACCOUNT_ID in GlobalVariables
                GlobalVariables.ACCOUNT_ID = activeAccountId

                ' Update the account details in the textbox
                JSONHelper.UpdateAccountDetailsTextBox(accountDetailsJson, txtAccountDetails)

                ' Display active account in the textbox
                txtAccounts.Text = $"Active Account: {activeAccountName} ({activeAccountId})"

                ' Set the selected item in the combo box to the active account
                For Each item As KeyValuePair(Of String, String) In cmbAccounts.Items
                    If item.Key = activeAccountId Then
                        cmbAccounts.SelectedItem = item
                        Exit For
                    End If
                Next

                ' Fetch and populate open trades
                Dim openTrades = Await apiHelper.FetchOpenTradesAsync()
                PopulateOpenTrades(openTrades)

                ' Fetch and populate trade history
                Dim tradeHistory = Await apiHelper.FetchTradeHistoryAsync()
                JSONHelper.PopulateTradeHistory(tradeHistory, txtHistory)
            Else
                MessageBox.Show("Failed to fetch account details.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            End If
        Catch ex As Exception
            MessageBox.Show($"Failed to fetch account details: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Function

    Private Async Sub cmbAPI_SelectedIndexChanged(sender As Object, e As EventArgs) Handles cmbAPI.SelectedIndexChanged
        ' Update BASE_URL and ENCRYPTION_KEY_URL based on the selected API
        Dim selectedApi As KeyValuePair(Of String, String) = CType(cmbAPI.SelectedItem, KeyValuePair(Of String, String))
        GlobalVariables.BASE_URL = selectedApi.Value
        GlobalVariables.UpdateUrls()

        ' Re-initialize session and fetch accounts based on the new API selection
        Await InitializeAndFetchAccountsAsync()
    End Sub

    Private Sub cmbEpic1_SelectedIndexChanged(sender As Object, e As EventArgs) Handles cmbEpic1.SelectedIndexChanged
        ' Save the selected value for cmbEpic1
        My.Settings.Epic1 = cmbEpic1.SelectedItem.ToString()
        My.Settings.Save()
    End Sub

    Private Sub txtAccountBalancePerc_LostFocus(sender As Object, e As EventArgs) Handles txtAccountBalancePerc.LostFocus
        ' Save the value of txtAccountBalancePerc to My.Settings.AccountBalancePerc
        My.Settings.AccountBalancePerc = txtAccountBalancePerc.Text
        My.Settings.Save()
    End Sub

    Private Async Sub cmdSwitch_Click(sender As Object, e As EventArgs) Handles cmdSwitch.Click
        Try

            If cmbAccounts.SelectedItem IsNot Nothing Then
                ' Cast the selected item as a KeyValuePair
                Dim selectedAccount As KeyValuePair(Of String, String) = CType(cmbAccounts.SelectedItem, KeyValuePair(Of String, String))
                Dim selectedAccountId As String = selectedAccount.Key

                ' Check if the selected account is different from the current ACCOUNT_ID
                If selectedAccountId <> GlobalVariables.ACCOUNT_ID Then
                    ' Update the ACCOUNT_ID
                    GlobalVariables.ACCOUNT_ID = selectedAccountId

                    ' Switch the account
                    Dim switchSuccess As Boolean = Await apiHelper.SwitchAccountAsync(selectedAccountId)
                    If switchSuccess Then
                        ' Update the active account display
                        txtAccounts.Text = $"Active Account: {selectedAccount.Value}"

                        ' Refresh the account data after switching
                        ' Fetch account details
                        Dim accountDetailsJson As String = Await apiHelper.FetchAccountDetailsAsync()
                        JSONHelper.UpdateAccountDetailsTextBox(accountDetailsJson, txtAccountDetails)

                        ' Fetch and populate open trades
                        Dim openTrades = Await apiHelper.FetchOpenTradesAsync()
                        PopulateOpenTrades(openTrades)

                        ' Fetch and populate trade history
                        Dim tradeHistory = Await apiHelper.FetchTradeHistoryAsync()
                        JSONHelper.PopulateTradeHistory(tradeHistory, txtHistory)
                    End If
                Else
                    MessageBox.Show("Selected account is already active.", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information)
                End If
            Else
                MessageBox.Show("Please select an account.", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information)
            End If
        Catch ex As InvalidCastException
            Debug.Print($"Error switching accounts: {ex.Message}")
        Catch ex As Exception
            MessageBox.Show($"Unexpected error: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub

    Private Async Function FetchAndStoreDealIdsAsync() As Task

        Try
            ' Fetch open trades
            Dim openTradesJson As String = Await apiHelper.FetchOpenTradesAsync()
            Dim openTrades As JObject = JObject.Parse(openTradesJson)

            For Each position As JObject In openTrades("positions")
                Dim epic As String = position("market")("epic").ToString()
                Dim dealId As String = position("position")("dealId").ToString()

                If epic = GlobalVariables.Epic1 Then
                    epic1DealId = dealId
                    LogTradeAction($"Epic1 Deal ID stored: {epic1DealId}")
                End If
            Next

        Catch ex As Exception
            LogTradeAction($"Error fetching and storing Deal IDs: {ex.Message}")
        End Try
    End Function

    Private Sub InitializeTimers()
        ' Initialize the Epic1 timer
        epic1Timer = New System.Windows.Forms.Timer()
        AddHandler epic1Timer.Tick, AddressOf OnEpic1TimerTick
        epic1Timer.Interval = 1000 ' 1-second interval

    End Sub

    Private Async Sub cmdStart_Click(sender As Object, e As EventArgs) Handles cmdStart.Click
        ' Validate SL Thresholds and Adjustments
        If Not ValidateThresholdsAndAdjustments() Then
            Exit Sub
        End If

        BotisRunning = True
        LogTradeAction("Start button clicked.") ' Add this log

        GlobalVariables.Epic1 = cmbEpic1.SelectedItem.ToString()
        GlobalVariables.AccountBalancePerc = txtAccountBalancePerc.Text

        NumberOfEpicsLoaded = 0

        Await FetchAndStoreDealIdsAsync()

        InitializeTimers()

        ' Add logs or breakpoints here to ensure these lines are reached
        Dim epic1Loaded = Await StartProcessForEpicAsync(GlobalVariables.Epic1)
        LogTradeAction($"Epic1 Loaded: {epic1Loaded}") ' Add this log

        If NumberOfEpicsLoaded = 0 Then
            LogTradeAction("No epics could be loaded. Bot will not start.")
            MessageBox.Show("No epics could be loaded. Please check your network or API settings.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Exit Sub
        ElseIf NumberOfEpicsLoaded = 1 Then
            LogTradeAction("Only one epic loaded. Allocating 100% of the balance to the loaded epic.")
        Else
            LogTradeAction("Both epics loaded successfully. Allocating 50% of the balance to each epic.")
        End If

        LogTradeAction($"Timers started for {GlobalVariables.Epic1}.")
    End Sub

    Private Function ValidateThresholdsAndAdjustments() As Boolean
        Dim thresholds As String() = txtSLThresholds.Text.Split(","c)
        Dim adjustments As String() = txtSLAdjustments.Text.Split(","c)

        ' Check if both arrays have the same length
        If thresholds.Length <> adjustments.Length Then
            MessageBox.Show("The number of SL Thresholds and SL Adjustments must be the same.", "Validation Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
            Return False
        End If

        ' Check if all entries are valid numbers or decimals
        For Each threshold As String In thresholds
            If Not Decimal.TryParse(threshold.Trim(), Nothing) Then
                MessageBox.Show($"Invalid entry in SL Thresholds: {threshold}", "Validation Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                Return False
            End If
        Next

        For Each adjustment As String In adjustments
            If Not Decimal.TryParse(adjustment.Trim(), Nothing) Then
                MessageBox.Show($"Invalid entry in SL Adjustments: {adjustment}", "Validation Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                Return False
            End If
        Next

        ' If all checks pass, return True
        Return True
    End Function
    Private Async Function StartProcessForEpicAsync(epic As String) As Task(Of Boolean)
        Try
            ' Fetch epic details and populate closing time
            Dim epicDetails As String = Await apiHelper.GetEpicDetailsAsync(epic)
            If String.IsNullOrEmpty(epicDetails) Then
                LogTradeAction($"Failed to load data for {epic}.")
                Return False
            End If

            ' Parse the fetched details and populate market times
            Dim parsedEpicDetails As JObject = JObject.Parse(epicDetails)
            Dim closingTime As DateTime = Await PopulateMarketTimes(parsedEpicDetails, epic)

            ' Set closing times for the respective epics
            If epic = GlobalVariables.Epic1 Then
                epic1ClosingTime = closingTime
            End If

            ' Start the timer for the specific epic
            If epic = GlobalVariables.Epic1 Then
                epic1Timer.Start()
            End If

            LogTradeAction($"{epic} process started with closing time: {closingTime}")
            NumberOfEpicsLoaded += 1
            Return True

        Catch ex As Exception
            LogTradeAction($"Error starting process for {epic}: {ex.Message}")
            Return False
        End Try
    End Function



    Private Sub ResetEpicFlags()
        Epic1InClosingMode = False
        Epic1CloseAttempts = 0
        epic1TradeClosed = False
        epic1TradeOpened = False
    End Sub


    Private Async Sub OnEpic1TimerTick(sender As Object, e As EventArgs) Handles epic1Timer.Tick
        Dim timeLeftEpic1 As TimeSpan = epic1ClosingTime - DateTime.Now

        ' Close trades if within 60 seconds and not yet closed
        ' Handle Epic1 independently if not synchronous
        If timeLeftEpic1.TotalSeconds <= GlobalVariables.SecondsBeforeCloseToExitTrade AndAlso Not epic1TradeClosed Then
            epic1TradeClosed = True
            Await CloseExistingTradeAsync(GlobalVariables.Epic1)
            Await FetchAndStoreDealIdsAsync()

            ' Refresh the txtOrders text box
            Dim openTrades = Await apiHelper.FetchOpenTradesAsync()
            PopulateOpenTrades(openTrades)

            ' Fetch and populate trade history
            Dim tradeHistory = Await apiHelper.FetchTradeHistoryAsync()
            JSONHelper.PopulateTradeHistory(tradeHistory, txtHistory)

        ElseIf timeLeftEpic1.TotalSeconds <= 30 AndAlso Not epic1TradeOpened Then
            epic1TradeOpened = True

            ' Create the trade with allocated balance
            Await CreateNewTradeAsync(GlobalVariables.Epic1)
            Await FetchAndStoreDealIdsAsync()

            ' Refresh the txtOrders text box
            Dim openTrades = Await apiHelper.FetchOpenTradesAsync()
            PopulateOpenTrades(openTrades)

            ' Fetch and populate trade history
            Dim tradeHistory = Await apiHelper.FetchTradeHistoryAsync()
            JSONHelper.PopulateTradeHistory(tradeHistory, txtHistory)
        End If

        ' Ensure no further action when timer hits zero, just restart the session
        If timeLeftEpic1.TotalSeconds <= 0 Then
            epic1Timer.Stop()

            LogTradeAction($"Session closed for {GlobalVariables.Epic1}. Waiting 10 minutes before starting the next session.")

            ' Wait 10 minutes before starting the next session
            Await Task.Delay(TimeSpan.FromMinutes(10))

            ' Reset flags for next session
            epic1TradeClosed = False
            epic1TradeOpened = False

            Await StartProcessForEpicAsync(GlobalVariables.Epic1)
        End If

        ' Update UI elements for Epic1
        txtEpic1Status.Text = $"{timeLeftEpic1.Days:D2}:{timeLeftEpic1.Hours:D2}:{timeLeftEpic1.Minutes:D2}:{timeLeftEpic1.Seconds:D2}"

    End Sub

    Private Async Sub OnGeneralTimerTick(sender As Object, e As EventArgs)
        Try
            ' Increment the counter each second
            generalTimerCounter += 1

            ' Fetch account details
            Dim accountDetailsJson As String = Await apiHelper.FetchAccountDetailsAsync()
            Dim accountDetails As JObject = JObject.Parse(accountDetailsJson)
            ' Update the account details in the textbox
            JSONHelper.UpdateAccountDetailsTextBox(accountDetailsJson, txtAccountDetails)

            ' Fetch and populate open trades
            Dim openTradesJson As String = Await apiHelper.FetchOpenTradesAsync()
            PopulateOpenTrades(openTradesJson)

            If chkUseTrailingSL.Checked = True And BotisRunning = True Then
                Await CheckAndAdjustStopLossAsync(openTradesJson)
            End If

        Catch ex As Exception
            LogTradeAction($"Error during general timer tick: {ex.Message}")
        End Try
    End Sub


    Private Async Function CheckAndAdjustStopLossAsync(openTradesJson As String) As Task
        ' Parse the JSON object
        Dim openTradesObject As JObject = JObject.Parse(openTradesJson)
        ' Extract the positions array
        Dim positionsArray As JArray = openTradesObject("positions")
        ' Check if there is at least one open trade
        If positionsArray.Count = 0 Then
            LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, No open trades found.")
            Exit Function
        End If

        ' Get the first (or only) open trade
        Dim tradePosition As JObject = positionsArray(0)("position")
        Dim marketData As JObject = positionsArray(0)("market")

        Dim dealId As String = tradePosition("dealId").ToString()
        Dim entryPrice As Decimal = tradePosition("level").ToObject(Of Decimal)()
        Dim currentPrice As Decimal = marketData("bid").ToObject(Of Decimal)() ' Use the bid price as the current price
        Dim currentStopLoss As Decimal = tradePosition("stopLevel").ToObject(Of Decimal)()

        ' Calculate percentage increase from entry
        Dim percentageIncrease As Decimal = ((currentPrice - entryPrice) / entryPrice) * 100D
        Dim percentageIncreaseRounded As Decimal = Math.Round(percentageIncrease, 4) ' Round to 4 decimal places for precision

        ' Get thresholds and stop loss adjustments from settings (entered in descending order)
        Dim thresholds As Decimal() = Array.ConvertAll(My.Settings.SLThresholds.Split(","c), Function(s) Decimal.Parse(s.Trim()))
        Dim adjustments As Decimal() = Array.ConvertAll(My.Settings.SLAdjustments.Split(","c), Function(s) Decimal.Parse(s.Trim()))

        ' Ensure both arrays have the same length
        If thresholds.Length <> adjustments.Length Then
            LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, The number of thresholds and stop loss adjustments must be the same.")
            Exit Function
        End If

        ' Loop through thresholds in order (from highest to lowest)
        For thresholdIndex As Integer = 0 To thresholds.Length - 1
            Dim threshold As Decimal = thresholds(thresholdIndex)
            Dim adjustment As Decimal = adjustments(thresholdIndex)

            ' Check if percentage increase meets or exceeds the threshold
            If percentageIncreaseRounded >= threshold Then
                ' Check if this threshold has already been acted upon
                If highestThresholdActedUpon < threshold Then
                    ' Calculate the new stop loss
                    Dim newStopLoss As Decimal = Math.Round(entryPrice * (1 + (adjustment / 100D)), 2)

                    ' Ensure the stop loss only increases
                    If newStopLoss > currentStopLoss Then
                        Try
                            ' Attempt to set the new stop loss
                            Dim updateResponse As JObject = Await apiHelper.UpdateStopLossAsync(dealId, newStopLoss)

                            ' Check if the update was successful by looking for "dealReference"
                            If updateResponse.ContainsKey("dealReference") Then
                                ' Log the update with detailed information
                                LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, Updated Stop Loss for dealId {dealId}.")
                                LogTradeAction($"Entry Price: {entryPrice}, Current Price: {currentPrice}, Current Stop Loss: {currentStopLoss}, New Stop Loss: {newStopLoss}")
                                LogTradeAction($"Percentage Increase: {percentageIncreaseRounded}%, Threshold Met: {threshold}%, Adjustment Applied: {adjustment}%")
                                ' Update the highest threshold acted upon
                                highestThresholdActedUpon = threshold
                                ' Exit the threshold loop after successful update
                                Exit For
                            Else
                                ' Log the error response
                                LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, Failed to update Stop Loss for dealId {dealId}. Response: {updateResponse.ToString()}")
                                ' Do not update highestThresholdActedUpon to allow retry
                            End If
                        Catch ex As Exception
                            ' Log any exceptions that occur during the update
                            LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, Error updating Stop Loss for dealId {dealId}: {ex.Message}")
                        End Try
                    Else
                        ' Optional: Log that the new stop loss is not higher than the current stop loss
                        LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, New stop loss {newStopLoss} is not higher than current stop loss {currentStopLoss} for dealId {dealId}. No update made.")
                    End If
                Else
                    ' Optional: Log that the threshold has already been acted upon
                    LogTradeAction($"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}, Threshold {threshold}% has already been acted upon for dealId {dealId}.")
                End If
                ' Since thresholds are in descending order, we can exit the loop after the first match
                Exit For
            End If
        Next
    End Function






    Private Async Function CloseExistingTradeAsync(epic As String) As Task
        Try
            Dim dealId As String = epic1DealId
            If String.IsNullOrEmpty(dealId) Then
                LogTradeAction($"No existing trade to close for {epic}.")
                Return
            End If

            GlobalVariables.CurrentEpic = epic ' Set the current epic in global variables
            GlobalVariables.DEAL_ID = epic1DealId ' Set the current deal ID in global variables

            Dim closeSuccess As Boolean = Await AttemptCloseTradeAsync(1)

            If closeSuccess Then
                If epic = GlobalVariables.Epic1 Then
                    epic1DealId = String.Empty
                End If
                LogTradeAction($"Trade for {epic} with Deal ID {dealId} closed successfully.")
            Else
                LogTradeAction($"Failed to close trade for {epic} with Deal ID {dealId}.")
            End If

        Catch ex As Exception
            LogTradeAction($"Error closing trade for {epic}: {ex.Message}")
        End Try
    End Function

    Private Async Function AttemptCloseTradeAsync(attemptNumber As Integer) As Task(Of Boolean)
        If String.IsNullOrEmpty(GlobalVariables.DEAL_ID) Then
            LogTradeAction($"No deal ID available to close on attempt {attemptNumber}.")
            Return False
        End If

        Try
            ' Log the request being sent to the API
            LogTradeAction($"Attempt {attemptNumber} to close trade with Deal ID: {GlobalVariables.DEAL_ID}")

            Dim jsonResponse As String = Await apiHelper.CloseOrderAsync(GlobalVariables.DEAL_ID)
            LogTradeAction($"API Response on attempt {attemptNumber} to close trade: {jsonResponse}")

            Dim parsedResponse As JObject = JObject.Parse(jsonResponse)
            Dim dealReference As String = parsedResponse("dealReference").ToString()

            ' Check if the trade was actually closed
            Dim openTrades As String = Await apiHelper.FetchOpenTradesAsync()
            If Not openTrades.Contains(GlobalVariables.DEAL_ID) Then
                GlobalVariables.DEAL_ID = String.Empty
                LogTradeAction($"Trade closed successfully on attempt {attemptNumber}.")
                Return True
            Else
                LogTradeAction($"Trade closure failed on attempt {attemptNumber}, trade still open.")
            End If

        Catch ex As HttpRequestException
            LogTradeAction($"HttpRequestException on attempt {attemptNumber}: {ex.Message}")
        Catch ex As Exception
            LogTradeAction($"Exception on attempt {attemptNumber}: {ex.Message}")
        End Try

        If attemptNumber < 3 Then
            Await Task.Delay(1000) ' Wait 1 second before retrying
            Return Await AttemptCloseTradeAsync(attemptNumber + 1)
        Else
            LogTradeAction("Failed to close trade after 3 attempts.")
            Return False
        End If
    End Function

    Private Async Function CreateNewTradeAsync(epic As String) As Task
        Try
            LogTradeAction($"Creating new trade for {epic} with ...")

            ' Update the current epic in global variables
            GlobalVariables.CurrentEpic = epic

            ' Use the existing TryToMakeTrade method to create a new trade
            Await TryToMakeTrade(isSimulation:=False)

            ' Store the Deal ID in the appropriate variable
            If GlobalVariables.TradeOpenedToday Then
                If epic = GlobalVariables.Epic1 Then
                    epic1DealId = GlobalVariables.DEAL_ID
                    My.Settings.Epic1DealID = epic1DealId
                End If

                LogTradeAction($"New trade created for {epic} with Deal ID: {GlobalVariables.DEAL_ID}")

                ' Fetch all open trades
                Dim openTradesJson As String = Await apiHelper.FetchOpenTradesAsync()
                LogTradeAction($"Open Trades JSON: {openTradesJson}") ' Log the raw JSON for debugging

                ' Parse the JSON
                Dim parsedJson As JObject = JObject.Parse(openTradesJson)

                ' Check if the 'positions' array exists
                If parsedJson("positions") IsNot Nothing Then
                    Dim openTrades As JArray = JArray.Parse(parsedJson("positions").ToString())

                    ' Find the trade for the current epic by checking inside the "market" object within "positions"
                    Dim currentTrade As JObject = openTrades.FirstOrDefault(Function(trade) trade("market")("epic").ToString() = epic)

                    If currentTrade IsNot Nothing Then
                        ' Extract the relevant trade details from the "position" object
                        Dim openPrice As Decimal = Decimal.Parse(currentTrade("position")("level").ToString())
                        Dim currentStopLoss As Decimal = Decimal.Parse(currentTrade("position")("stopLevel").ToString())
                        LogTradeAction($"Open price for {epic} trade: {openPrice}, Current stop loss: {currentStopLoss}")

                        ' Correct calculation for the new stop loss based on account balance percentage
                        Dim stopLossPercentage As Decimal = My.Settings.StopLoss / 100
                        Dim priceDrop As Decimal = openPrice * stopLossPercentage
                        Dim newStopLoss As Decimal = openPrice - priceDrop

                        LogTradeAction($"Calculated new stop loss for {epic}: {newStopLoss}")

                        ' Update the stop loss for the current trade
                        Dim dealId As String = currentTrade("position")("dealId").ToString()
                        Dim updateResponse As String = Await apiHelper.UpdateStopLossAsync(dealId, newStopLoss)


                        'SAVE TO SETTINGS
                        My.Settings.Epic1EntryPrice = openPrice
                        My.Settings.Epic1SL = newStopLoss

                        ' Log confirmation that the stop loss has been updated
                        LogTradeAction($"Stop loss for trade with Deal ID {dealId} updated to {newStopLoss}. API response: {updateResponse}")
                    Else
                        LogTradeAction($"Trade for epic {epic} not found in open trades.")
                    End If
                Else
                    LogTradeAction("No 'positions' array found in the JSON response.")
                End If

            Else
                LogTradeAction($"Failed to create a new trade for {epic}.")
            End If

        Catch ex As Exception
            LogTradeAction($"Error creating trade for {epic}: {ex.Message}")
        End Try
    End Function



    Private Async Function TryToMakeTrade(isSimulation As Boolean) As Task
        Try
            LogTradeAction("Entering TryToMakeTrade method.")

            ' Fetch epic details to get the bid and ask prices
            Dim epicDetailsJson As String = Await apiHelper.GetEpicDetailsAsync(GlobalVariables.CurrentEpic)
            Dim epicDetails As JObject = JObject.Parse(epicDetailsJson)

            ' Extract bid and ask prices
            GlobalVariables.BidPrice = epicDetails("snapshot")("bid").ToObject(Of Decimal)()
            GlobalVariables.AskPrice = epicDetails("snapshot")("offer").ToObject(Of Decimal)()
            GlobalVariables.MidPrice = (GlobalVariables.BidPrice + GlobalVariables.AskPrice) / 2
            LogTradeAction($"Fetched Bid Price: {GlobalVariables.BidPrice}, Ask Price: {GlobalVariables.AskPrice}, Calculated Mid Price: {GlobalVariables.MidPrice}")

            ' Fetch dealing rules for the current epic
            Dim dealingRules = epicDetails("dealingRules")

            ' Extract relevant dealing rules
            GlobalVariables.MinDealSize = dealingRules("minDealSize")("value").ToObject(Of Decimal)()
            GlobalVariables.MaxDealSize = dealingRules("maxDealSize")("value").ToObject(Of Decimal)()
            GlobalVariables.MinSizeIncrement = dealingRules("minSizeIncrement")("value").ToObject(Of Decimal)()
            LogTradeAction($"Dealing Rules - Min Deal Size: {GlobalVariables.MinDealSize}, Max Deal Size: {GlobalVariables.MaxDealSize}, Min Size Increment: {GlobalVariables.MinSizeIncrement}")

            ' Fetch and update the account balance for the selected account
            Dim accountDetailsJson As String = Await apiHelper.FetchAccountDetailsAsync()
            Dim accountDetails As JObject = JObject.Parse(accountDetailsJson)

            ' Find the selected account's details
            Dim selectedAccount As KeyValuePair(Of String, String) = CType(cmbAccounts.SelectedItem, KeyValuePair(Of String, String))
            Dim selectedAccountDetails As JObject = accountDetails("accounts").FirstOrDefault(Function(a) a("accountId").ToString() = selectedAccount.Key)

            If selectedAccountDetails IsNot Nothing Then
                ' Update the AccountBalance in GlobalVariables
                GlobalVariables.AccountBalance = selectedAccountDetails("balance")("available").ToObject(Of Decimal)()
                LogTradeAction($"Updated Account Balance: {GlobalVariables.AccountBalance}")
            Else
                LogTradeAction("Selected account not found. Cannot proceed with trade.")
                Return
            End If

            ' Store the current bid price as the trade open price
            GlobalVariables.TradeOpenPrice = GlobalVariables.BidPrice
            LogTradeAction($"Trade Open Price: {GlobalVariables.TradeOpenPrice}")

            ' Store the account balance before the trade
            GlobalVariables.BalanceBeforeTrade = GlobalVariables.AccountBalance
            LogTradeAction($"Balance Before Trade: {GlobalVariables.BalanceBeforeTrade}")

            ' Use the bid price directly for the current price
            Dim currentPrice As Decimal = GlobalVariables.BidPrice
            LogTradeAction($"Current Bid Price: {currentPrice}")

            Dim leverage = Await apiHelper.GetLeverageFromSystemAsync()
            LogTradeAction($"Leverage: {leverage}")

            ' Check the number of active trades to determine balance allocation
            Dim activeTradesJson As String = Await apiHelper.FetchOpenTradesAsync()
            Dim activeTrades As JObject = JObject.Parse(activeTradesJson)
            Dim activeTradesCount As Integer = activeTrades("positions").Count()

            ' Adjust trade size based on the balance of the account to use
            Dim tradeSize = GlobalVariables.AccountBalance * (GlobalVariables.AccountBalancePerc / 100D) * leverage / currentPrice


            LogTradeAction($"Adjusted Trade Size (before floor adjustment): {tradeSize}")

            ' Ensure trade size complies with dealing rules
            If tradeSize < GlobalVariables.MinDealSize Then
                tradeSize = GlobalVariables.MinDealSize
            ElseIf tradeSize > GlobalVariables.MaxDealSize Then
                tradeSize = GlobalVariables.MaxDealSize
            End If

            tradeSize = Math.Floor(tradeSize / GlobalVariables.MinSizeIncrement) * GlobalVariables.MinSizeIncrement
            LogTradeAction($"Trade Size (after floor adjustment): {tradeSize}")

            ' Calculate the stop loss using the percentage from My.Settings.StopLoss
            Dim stopLossPercentage As Decimal = My.Settings.StopLoss / 100D
            Dim stopLossLevel = GlobalVariables.BidPrice * (1 - stopLossPercentage)
            LogTradeAction($"Stop Loss Level: {stopLossLevel}")

            If chkSimTrade.Checked = False Then
                Dim jsonResponse = Await apiHelper.CreateOrderAsync(GlobalVariables.CurrentEpic, "BUY", tradeSize, False, stopLossLevel)
                LogTradeAction($"API Response: {jsonResponse}")

                Dim parsedResponse As JObject = JObject.Parse(jsonResponse)
                GlobalVariables.DEAL_ID = parsedResponse("dealReference").ToString()
                LogTradeAction($"Trade successfully made. Deal ID: {GlobalVariables.DEAL_ID}")
                GlobalVariables.TradeOpenedToday = True
                GlobalVariables.LastTradeOpenTime = DateTime.UtcNow
            Else
                LogTradeAction($"Sim trade successfully made....[SIMULATION TRADE]")
                GlobalVariables.TradeOpenedToday = True
                GlobalVariables.LastTradeOpenTime = DateTime.UtcNow
            End If

        Catch ex As Exception
            LogTradeAction($"Error in TryToMakeTrade: {ex.Message}")
        End Try
    End Function

    Private Sub PopulateOpenTrades(jsonResponse As String)
        Try
            Dim parsedJson As JObject = JObject.Parse(jsonResponse)
            Dim positions As JArray = parsedJson("positions")

            ' Clear the RichTextBox before appending new content
            txtOrders.Clear()


            For Each position As JObject In positions
                Dim dealId As String = position("position")("dealId").ToString()
                Dim epic As String = position("market")("epic").ToString()
                Dim direction As String = position("position")("direction").ToString()
                Dim size As Decimal = position("position")("size").ToObject(Of Decimal)()
                Dim level As Decimal = position("position")("level").ToObject(Of Decimal)()
                Dim bidPrice As Decimal = position("market")("bid").ToObject(Of Decimal)()
                Dim total As Decimal = size * level

                ' Calculate P&L as a percentage
                Dim pnlPercentage As Decimal = ((bidPrice - level) / level) * 100D

                ' Calculate P&L amount in USD
                Dim pnlAmount As Decimal = (bidPrice - level) * size

                'TRAILING SL
                GlobalVariables.Epic1EntryPrice = bidPrice
                GlobalVariables.Epic1ProfitLoss = pnlAmount

                ' Check if the stopLevel property exists and calculate Stop Loss as a percentage
                Dim stopLossPercentage As Decimal
                If position("position")("stopLevel") IsNot Nothing Then
                    Dim stopLevel As Decimal = position("position")("stopLevel").ToObject(Of Decimal)()
                    stopLossPercentage = ((stopLevel - level) / level) * 100D
                Else
                    stopLossPercentage = 0 ' Or set a default value or message indicating no stop loss is set
                End If

                ' Format total, P&L amount, and Stop Loss with commas
                Dim totalFormatted As String = total.ToString("N2")
                Dim pnlAmountFormatted As String = pnlAmount.ToString("N2")

                ' Append Deal ID and Epic
                txtOrders.AppendText($"" & Environment.NewLine)
                txtOrders.AppendText($"Deal ID: {dealId}" & Environment.NewLine)
                txtOrders.AppendText($"{epic}: {totalFormatted}" & Environment.NewLine)
                ' Append P&L with color formatting
                txtOrders.AppendText("P&L: ")

                If pnlPercentage >= 0 Then
                    txtOrders.SelectionColor = Color.Cyan
                    txtOrders.AppendText($"{pnlAmountFormatted} (+{pnlPercentage:F2}%)" & Environment.NewLine)
                Else
                    txtOrders.SelectionColor = Color.Red
                    txtOrders.AppendText($"{pnlAmountFormatted} ({pnlPercentage:F2}%)" & Environment.NewLine)
                End If
                txtOrders.SelectionColor = Color.Black ' Reset color to default for the rest of the text

                ' Append Stop Loss
                txtOrders.AppendText($"StopLoss: {stopLossPercentage:F2}%" & Environment.NewLine)
                'txtOrders.AppendText(New String("-"c, 46) & Environment.NewLine)
            Next

        Catch ex As Exception
            Console.WriteLine("Error parsing open trades JSON: " & ex.Message)
        End Try

        UpdateStatusText()
    End Sub

    Private Sub UpdateStatusText()
        ' Implementation to update the status text based on the current status of trades
    End Sub

    Private Sub cmdStop_Click(sender As Object, e As EventArgs)
        epic1Timer.Stop()
        LogTradeAction("Timers stopped.")
    End Sub

    Private Async Sub cmdEpic1Simulate_Click(sender As Object, e As EventArgs) Handles cmdEpic1Simulate.Click
        Await SimulateCloseAsync(GlobalVariables.Epic1)
    End Sub

    Private Async Function SimulateCloseAsync(epic As String) As Task
        Try
            LogTradeAction($"Simulate button clicked for {epic}")

            ' Set the simulated close time to 65 seconds from now
            epic1ClosingTime = DateTime.Now.AddSeconds(65)
            epic1Timer.Start()

            LogTradeAction($"Starting session close simulation for {epic}")

        Catch ex As Exception
            LogTradeAction($"Error in cmdSimulate_Click: {ex.Message}")
        End Try
    End Function



    Private Async Function PopulateMarketTimes(parsedJson As JObject, epic As String) As Task(Of DateTime)
        Dim instrument As JObject = parsedJson("instrument")
        Dim openingHours As JObject = instrument("openingHours")

        Dim now As DateTime = DateTime.UtcNow ' Use UTC to match with the API time zone.
        Dim currentSessionClosingTime As DateTime? = Nothing
        Dim dayFound As Boolean = False

        ' Array of days in the week ordered based on DayOfWeek enum
        Dim daysOfWeek As String() = {"sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}
        Dim currentDayIndex As Integer = Array.IndexOf(daysOfWeek, now.DayOfWeek.ToString().ToLower())

        ' Iterate through each day starting from the current day
        For i As Integer = 0 To daysOfWeek.Length - 1
            Dim day As String = daysOfWeek((currentDayIndex + i) Mod daysOfWeek.Length)
            Dim times As JArray = TryCast(openingHours(day.Substring(0, 3)), JArray)

            If times IsNot Nothing AndAlso times.Count > 0 Then
                ' Use the first time range of the day
                Dim timeRange As String = times(0).ToString()
                Dim timeParts As String() = timeRange.Split(New String() {" - "}, StringSplitOptions.None)
                Dim openTime As TimeSpan = TimeSpan.Parse(timeParts(0))
                Dim closeTime As TimeSpan = TimeSpan.Parse(timeParts(1))

                ' Calculate the closing time for this session and adjust for UTC
                Dim closingDateTime As DateTime = now.Date.AddDays(i).Add(closeTime)

                ' Handle case where closing time is after midnight (market closes the next day)
                If closeTime < openTime Then
                    closingDateTime = closingDateTime.AddDays(1)
                End If

                ' Check if the closing time is valid for the next session (after now)
                If closingDateTime > now Then
                    currentSessionClosingTime = closingDateTime
                    dayFound = True
                    Exit For
                End If
            End If
        Next

        If currentSessionClosingTime.HasValue Then
            ' Convert the closing time from UTC to Dubai time by adding 4 hours
            Dim dubaiClosingTime As DateTime = currentSessionClosingTime.Value.AddHours(4)

            ' Log the closing time
            LogTradeAction($"Next valid session found for {epic}. Session closing time in Dubai time: {dubaiClosingTime}")

            Return dubaiClosingTime ' Return the Dubai closing time if needed
        Else
            ' Default to midnight of the current day in UTC, converted to Dubai time
            Dim defaultTime As DateTime = now.Date.AddHours(4) ' Midnight UTC is 4 AM in Dubai time
            LogTradeAction($"No valid session found for {epic}. Defaulting to midnight Dubai time: {defaultTime}")
            Return defaultTime
        End If
    End Function


    Private Sub ClearLogFile()
        Try
            If IO.File.Exists(LOG_FILE_PATH) Then
                IO.File.WriteAllText(LOG_FILE_PATH, String.Empty)
                Console.WriteLine("Log file cleared.")
            End If
        Catch ex As Exception
            Console.WriteLine($"Error clearing log file: {ex.Message}")
        End Try
    End Sub

    ' Helper method to log actions (now in the form)
    Public Sub LogTradeAction(message As String)

        Dim timestamp As String = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff")
        Dim logEntry As String = $"{timestamp}, {message}"
        'System.IO.File.AppendAllText(LOG_FILE_PATH, logEntry & Environment.NewLine)
        Console.WriteLine(logEntry)

        ' Optionally, log to the status textbox
        If Me.InvokeRequired Then
            Me.Invoke(New Action(Sub()
                                     txtStatus.Text = $"{logEntry}{Environment.NewLine}{txtStatus.Text}"
                                 End Sub))
        Else
            txtStatus.Text = $"{logEntry}{Environment.NewLine}{txtStatus.Text}"
        End If

    End Sub

    Private Sub txtSL_LostFocus(sender As Object, e As EventArgs) Handles txtSL.LostFocus
        Dim stopLossValue As Double

        If Double.TryParse(txtSL.Text, stopLossValue) Then
            My.Settings.StopLoss = stopLossValue
            My.Settings.Save()
        Else
            MessageBox.Show("Please enter a valid stop loss percentage.", "Invalid Input", MessageBoxButtons.OK, MessageBoxIcon.Warning)
        End If
    End Sub
    Private Sub txtSLThresholds_LostFocus(sender As Object, e As EventArgs) Handles txtSLThresholds.LostFocus

        My.Settings.SLThresholds = txtSLThresholds.Text
        My.Settings.SLAdjustments = txtSLAdjustments.Text
        My.Settings.Save()

    End Sub

    Private Sub txtSLAdjustments_LostFocus(sender As Object, e As EventArgs) Handles txtSLAdjustments.LostFocus

        My.Settings.SLThresholds = txtSLThresholds.Text
        My.Settings.SLAdjustments = txtSLAdjustments.Text
        My.Settings.Save()

    End Sub

    Private Async Sub cmdInst_Click(sender As Object, e As EventArgs) Handles cmdInst.Click
        Try
            ' Fetch all instruments from the API
            Dim instrumentsJson As String = Await apiHelper.FetchAllInstrumentsAsync()

            ' Display the fetched instruments in txtHistory
            txtHistory.Text = instrumentsJson
        Catch ex As Exception
            MessageBox.Show($"Failed to fetch instruments: {ex.Message}", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
        End Try
    End Sub



End Class
Public Class Position
    Public Property contractSize As Decimal
    Public Property createdDate As DateTime
    Public Property createdDateUTC As DateTime
    Public Property dealId As String
    Public Property dealReference As String
    Public Property workingOrderId As String
    Public Property size As Decimal
    Public Property leverage As Integer
    Public Property upl As Decimal
    Public Property direction As String
    Public Property level As Decimal
    Public Property currency As String
    Public Property guaranteedStop As Boolean
    Public Property stopLevel As Decimal
    Public Property trailingStop As Boolean
End Class

' Define the Market class to match the JSON structure
Public Class Market
    Public Property instrumentName As String
    Public Property expiry As String
    Public Property marketStatus As String
    Public Property epic As String
    Public Property symbol As String
    Public Property instrumentType As String
    Public Property lotSize As Decimal
    Public Property high As Decimal
    Public Property low As Decimal
    Public Property percentageChange As Decimal
    Public Property netChange As Decimal
    Public Property bid As Decimal
    Public Property offer As Decimal
    Public Property updateTime As DateTime
    Public Property updateTimeUTC As DateTime
    Public Property delayTime As Integer
    Public Property streamingPricesAvailable As Boolean
    Public Property scalingFactor As Integer
    Public Property marketModes As String()
End Class
