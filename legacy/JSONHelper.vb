Imports Newtonsoft.Json
Imports Newtonsoft.Json.Linq
Imports System.Globalization
Imports System.Text
Imports System.Windows.Forms

Module JSONHelper


    ' Updates the account details TextBox with formatted data
    Public Sub UpdateAccountDetailsTextBox(jsonResponse As String, txtAccountDetails As TextBox)
        Try
            Dim parsedJson As JObject = JObject.Parse(jsonResponse)
            Dim output As New StringBuilder()

            output.AppendLine($"")
            ' Find the active account based on the ACCOUNT_ID
            For Each account As JObject In parsedJson("accounts")
                If account("accountId").ToString() = GlobalVariables.ACCOUNT_ID Then
                    output.AppendLine($"- Account Name: {account("accountName")}")
                    output.AppendLine($"- Balance: {account("balance")("balance")}")
                    output.AppendLine($"- Profit/Loss: {account("balance")("profitLoss")}")
                    output.AppendLine($"- Available: {account("balance")("available")}")
                    output.AppendLine($"- Currency: {account("currency")}")
                    output.AppendLine()
                    Exit For
                End If
            Next

            ' Log to verify the output
            Console.WriteLine("Updated account details text box with: " & output.ToString())

            ' Ensure this is executed on the UI thread
            If txtAccountDetails.InvokeRequired Then
                txtAccountDetails.Invoke(New Action(Sub() txtAccountDetails.Text = output.ToString()))
            Else
                txtAccountDetails.Text = output.ToString()
            End If

        Catch ex As JsonReaderException
            If txtAccountDetails.InvokeRequired Then
                txtAccountDetails.Invoke(New Action(Sub() txtAccountDetails.Text = $"Error parsing JSON: {ex.Message}"))
            Else
                txtAccountDetails.Text = $"Error parsing JSON: {ex.Message}"
            End If
            Console.WriteLine("Error parsing account details JSON: " & ex.Message)
        End Try
    End Sub



    ' Updates the GlobalVariables with the snapshot details extracted from the JSON

    ' New method to populate trade history
    Public Sub PopulateTradeHistory(jsonResponse As String, txtHistory As TextBox)
        Try
            Dim parsedJson As JObject = JObject.Parse(jsonResponse)
            Dim transactions As JArray = parsedJson("transactions")

            ' Define the column widths for neat alignment
            Dim dateColumnWidth As Integer = 20
            Dim instrumentColumnWidth As Integer = 15
            Dim sizeColumnWidth As Integer = 10
            Dim pnlColumnWidth As Integer = 12  ' Increased to prevent overlap

            ' Sort transactions by date in descending order
            Dim sortedTransactions = transactions.OrderByDescending(Function(t) DateTime.Parse(t("dateUtc").ToString())).ToArray()

            Dim sb As New StringBuilder()

            ' Create the header row with padded columns
            sb.AppendLine(
            $"{PadRight("Date", dateColumnWidth)}" &
            $"{PadRight("Instrument", instrumentColumnWidth)}" &
            $"{PadRight("Size", sizeColumnWidth)}" &
            $"{PadRight("P/L", pnlColumnWidth)}"
        )

            ' Create the data rows with padded columns
            For Each transaction As JObject In sortedTransactions
                Dim dateUtc As String = transaction("dateUtc").ToString()
                Dim instrumentName As String = transaction("instrumentName").ToString()
                Dim size As Decimal = transaction("size").ToObject(Of Decimal)()
                Dim profitLoss As String = If(transaction.ContainsKey("profitLoss"), transaction("profitLoss").ToString(), "N/A")

                sb.AppendLine(
                $"{PadRight(dateUtc, dateColumnWidth)}" &
                $"{PadRight(instrumentName, instrumentColumnWidth)}" &
                $"{PadLeft(size.ToString("F2"), sizeColumnWidth)}" &
                $"{PadLeft(profitLoss, pnlColumnWidth)}"
            )
            Next

            If txtHistory.InvokeRequired Then
                txtHistory.Invoke(New Action(Sub() txtHistory.Text = sb.ToString()))
            Else
                txtHistory.Text = sb.ToString()
            End If

        Catch ex As Exception
            Console.WriteLine("Error parsing trade history JSON: " & ex.Message)
        End Try
    End Sub


    ' Helper functions to pad strings
    Private Function PadRight(value As String, totalWidth As Integer) As String
        Return value.PadRight(totalWidth)
    End Function

    Private Function PadLeft(value As String, totalWidth As Integer) As String
        Return value.PadLeft(totalWidth)
    End Function

End Module
