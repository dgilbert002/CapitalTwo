Public Class GlobalVariables

    ' Define the Position class to match the JSON structure


    ' Tokens and trade details
    Public Shared CST_TOKEN As String = String.Empty
    Public Shared SECURITY_TOKEN As String = String.Empty

    ' Replace CURRENT_EPIC with Epic1 and Epic2
    Public Shared Epic1 As String = "TECL"
    Public Shared CurrentEpic As String = "TECL"


    Public Shared DEAL_ID As String = String.Empty
    Public Shared OrderResponse As String = String.Empty
    Public Shared TradeDetails As String = String.Empty
    Public Shared UpdateResponse As String = String.Empty
    Public Shared CloseResponse As String = String.Empty

    Public Shared ACCOUNT_ID As String = ""
    Public Shared BASE_URL As String = String.Empty
    Public Const API_KEY As String = "QxZZYB9ZtE3FDggx"
    Public Shared ENCRYPTION_KEY_URL As String = String.Empty
    Public Const IDENTIFIER As String = "dean2021q1@gmail.com"
    Public Const PASSWORD As String = "Password1!"


    Public Shared SecondsBeforeCloseToExitTrade As Integer = 60

    ' Dealing Rules and Market Data
    Public Shared MinStepDistance As Decimal
    Public Shared MinDealSize As Decimal
    Public Shared MaxDealSize As Decimal
    Public Shared MinSizeIncrement As Decimal
    Public Shared MinGuaranteedStopDistance As Decimal
    Public Shared MinStopOrProfitDistance As Decimal
    Public Shared MaxStopOrProfitDistance As Decimal
    Public Shared MarketOrderPreference As String
    Public Shared TrailingStopsPreference As String

    ' Additional Trade Parameters
    Public Shared LotSize As Decimal
    Public Shared MarginFactor As Decimal
    Public Shared MarginFactorUnit As String

    ' Other parameters
    Public Shared AccountBalancePerc As Decimal
    Public Shared AccountBalance As Decimal
    Public Shared CurrentBid As Decimal
    Public Shared CurrentOffer As Decimal
    Public Shared MidPrice As Decimal
    Public Shared BidPrice As Decimal
    Public Shared AskPrice As Decimal
    Public Shared OfferPrice As Decimal
    Public Shared CurrentPrice As Decimal
    Public Shared CurrentEpicName As String
    Public Shared TradeOpenPrice As Decimal
    Public Shared BalanceBeforeTrade As Decimal

    'Trailing SL variables
    Public Shared Epic1EntryPrice As Decimal
    Public Shared Epic1ProfitLoss As Decimal

    ' Leverage
    Public Shared CurrentLeverage As Decimal

    ' Trading parameters and variables
    Public Shared TradeOpenedToday As Boolean = False
    Public Shared MarketOpen As Boolean = False
    Public Shared LastTradeOpenTime As DateTime = DateTime.MinValue

    ' Store adjusted closing and opening times for each day
    Public Shared ClosingTimes As New Dictionary(Of DayOfWeek, DateTime)
    Public Shared OpeningTimes As New Dictionary(Of DayOfWeek, DateTime)

    ' Track the current market day for trading
    Public Shared LastTradeDay As DayOfWeek = DayOfWeek.Sunday

    ' New variable to store today's closing time
    Public Shared TodayClosingTime As DateTime

    ' New variable to store next opening time after the market closes
    Public Shared NextOpeningTime As DateTime

    ' Track the number of epics loaded successfully
    Public Shared NumberOfEpicsLoaded As Integer = 0

    ' Method to update the URLs based on the current BASE_URL
    Public Shared Sub UpdateUrls()
        ENCRYPTION_KEY_URL = BASE_URL & "/session/encryptionKey"
    End Sub


End Class
