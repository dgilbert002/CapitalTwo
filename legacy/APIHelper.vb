Imports System.Net.Http
Imports System.Text
Imports Newtonsoft.Json
Imports Newtonsoft.Json.Linq

Public Class ApiHelper
    Private ReadOnly client As HttpClient
    Private ReadOnly mainForm As frmCapitalOne
    Private ReadOnly httpClient As HttpClient

    Public Sub New(apiKey As String, form As frmCapitalOne)
        client = New HttpClient()
        client.DefaultRequestHeaders.Add("X-CAP-API-KEY", apiKey)
        mainForm = form
    End Sub
    Public Async Function PingServiceAsync() As Task(Of String)
        Dim result As String = String.Empty

        Try
            Dim request As New HttpRequestMessage(HttpMethod.Get, $"{GlobalVariables.BASE_URL}/ping")
            request.Headers.Add("X-SECURITY-TOKEN", GlobalVariables.SECURITY_TOKEN)
            request.Headers.Add("CST", GlobalVariables.CST_TOKEN)

            Dim response As HttpResponseMessage = Await client.SendAsync(request)

            If response.IsSuccessStatusCode Then
                result = Await response.Content.ReadAsStringAsync()
            Else
                result = $"Ping failed with status code: {response.StatusCode}"
            End If
        Catch ex As Exception
            result = $"Exception during ping: {ex.Message}"
        End Try

        Return result
    End Function
    Public Async Function GetSessionAsync(url As String, identifier As String, password As String) As Task(Of String)
        Dim payload As New With {
            Key .identifier = identifier,
            Key .password = password
        }

        Dim response As HttpResponseMessage = Await PostAsync(url, payload, String.Empty, String.Empty)
        If response Is Nothing Then
            Throw New Exception("The response from PostAsync is null.")
        End If

        response.EnsureSuccessStatusCode()

        If response.Headers.Contains("CST") Then
            GlobalVariables.CST_TOKEN = response.Headers.GetValues("CST").FirstOrDefault()
        End If

        If response.Headers.Contains("X-SECURITY-TOKEN") Then
            GlobalVariables.SECURITY_TOKEN = response.Headers.GetValues("X-SECURITY-TOKEN").FirstOrDefault()
        End If

        Return Await response.Content.ReadAsStringAsync()
    End Function

    Public Async Function EstablishSessionAsync() As Task(Of Boolean)
        Try
            Dim sessionResponse As String = Await GetSessionAsync(GlobalVariables.BASE_URL & "/session", GlobalVariables.IDENTIFIER, GlobalVariables.PASSWORD)
            Return Not String.IsNullOrEmpty(GlobalVariables.CST_TOKEN) AndAlso Not String.IsNullOrEmpty(GlobalVariables.SECURITY_TOKEN)
        Catch ex As Exception
            mainForm.LogTradeAction($"Failed to establish session: {ex.Message}")
            Return False
        End Try
    End Function

    Public Async Function SwitchAccountAsync(accountId As String) As Task(Of Boolean)
        Try
            Dim payload As New With {
                .accountId = accountId
            }
            Dim jsonPayload As String = JsonConvert.SerializeObject(payload)
            Dim content As New StringContent(jsonPayload, Encoding.UTF8, "application/json")

            SetSecurityHeaders(GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)

            Dim response As HttpResponseMessage = Await client.PutAsync(GlobalVariables.BASE_URL & "/session", content)
            If response.IsSuccessStatusCode Then
                Return True
            Else
                Dim errorDetails As String = Await response.Content.ReadAsStringAsync()
                mainForm.LogTradeAction($"Failed to switch account: {errorDetails}")
            End If
        Catch ex As Exception
            mainForm.LogTradeAction($"Failed to switch account: {ex.Message}")
        End Try

        Return False
    End Function

    Public Async Function GetLeverageFromSystemAsync() As Task(Of Decimal)
        Try
            Dim endpoint As String = "/accounts/preferences"
            Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
            response.EnsureSuccessStatusCode()

            Dim jsonResponse As String = Await response.Content.ReadAsStringAsync()
            Dim parsedJson As JObject = JObject.Parse(jsonResponse)

            Dim leverageSettings As JObject = parsedJson("leverages")
            Dim leverage As Decimal = leverageSettings("SHARES")("current").ToObject(Of Decimal)()

            GlobalVariables.CurrentLeverage = leverage

            Return leverage
        Catch ex As Exception
            mainForm.LogTradeAction($"Error retrieving leverage: {ex.Message}")
            Return 1
        End Try
    End Function

    Public Async Function FetchAccountDetailsAsync() As Task(Of String)
        Dim endpoint As String = "/accounts"
        Dim attempts As Integer = 0
        Dim maxRetries As Integer = 5
        Dim delayBetweenRetries As Integer = 1000
        Dim success As Boolean = False

        Do
            Try
                attempts += 1

                Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
                response.EnsureSuccessStatusCode()

                success = True
                Return Await response.Content.ReadAsStringAsync()

            Catch ex As HttpRequestException
                mainForm.LogTradeAction($"Error fetching account details on attempt {attempts}: {ex.Message}")

                If attempts >= maxRetries Then
                    mainForm.LogTradeAction("Max retry attempts reached.")
                    Exit Do
                End If
            End Try

            If Not success Then
                mainForm.LogTradeAction($"Retrying in {delayBetweenRetries}ms...")
                Await Task.Delay(delayBetweenRetries)
            End If

        Loop While attempts < maxRetries

        Return String.Empty
    End Function

    Public Async Function GetEpicDetailsAsync(epic As String) As Task(Of String)
        Dim endpoint As String = $"/markets/{epic}"
        Dim attempts As Integer = 0
        Dim maxRetries As Integer = 5
        Dim delayBetweenRetries As Integer = 1000
        Dim success As Boolean = False

        Do
            Try
                attempts += 1

                Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
                response.EnsureSuccessStatusCode()

                success = True
                Return Await response.Content.ReadAsStringAsync()

            Catch ex As HttpRequestException
                mainForm.LogTradeAction($"Error fetching market details for epic {epic} on attempt {attempts}: {ex.Message}")

                If attempts >= maxRetries Then
                    mainForm.LogTradeAction("Max retry attempts reached.")
                    Exit Do
                End If
            End Try

            If Not success Then
                mainForm.LogTradeAction($"Retrying in {delayBetweenRetries}ms...")
                Await Task.Delay(delayBetweenRetries)
            End If

        Loop While attempts < maxRetries

        Return String.Empty
    End Function

    Public Async Function FetchOpenTradesAsync() As Task(Of String)
        Dim attempts As Integer = 0
        Dim maxRetries As Integer = 5
        Dim delayBetweenRetries As Integer = 1000
        Dim lastException As Exception = Nothing

        While attempts < maxRetries
            Try
                attempts += 1
                Dim endpoint As String = "/positions"
                Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
                response.EnsureSuccessStatusCode()
                Return Await response.Content.ReadAsStringAsync()

            Catch ex As Exception
                lastException = ex
                mainForm.LogTradeAction($"Error during fetching open trades on attempt {attempts}: {ex.Message}")
                If attempts >= maxRetries Then
                    mainForm.LogTradeAction($"Failed to fetch open trades after {attempts} attempts. Will attempt to reinitialize session.")
                    Exit While
                End If
            End Try

            Await Task.Delay(delayBetweenRetries)
        End While

        Return Nothing
    End Function

    Public Async Function CreateOrderAsync(epic As String, direction As String, size As Decimal, Optional guaranteedStop As Boolean = False, Optional stopLevel As Decimal? = Nothing, Optional profitLevel As Decimal? = Nothing) As Task(Of String)
        Dim endpoint As String = "/positions"
        Dim payload As New With {
            Key .epic = epic,
            Key .direction = direction,
            Key .size = size,
            Key .guaranteedStop = guaranteedStop,
            Key .stopLevel = stopLevel,
            Key .profitLevel = profitLevel
        }
        Dim response As HttpResponseMessage = Await PostAsync(GlobalVariables.BASE_URL & endpoint, payload, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
        response.EnsureSuccessStatusCode()
        Return Await response.Content.ReadAsStringAsync()
    End Function

    Public Async Function CloseOrderAsync(dealId As String) As Task(Of String)
        Try
            Dim endpoint As String = $"/positions/{dealId}"
            Dim response As HttpResponseMessage = Await DeleteAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)

            If response.IsSuccessStatusCode Then
                Return Await response.Content.ReadAsStringAsync()
            Else
                Dim errorContent As String = Await response.Content.ReadAsStringAsync()
                mainForm.LogTradeAction($"Error closing order. Status code: {response.StatusCode}, Error: {errorContent}")
                Throw New HttpRequestException($"Failed to close order. Status code: {response.StatusCode}, Error: {errorContent}")
            End If
        Catch ex As Exception
            mainForm.LogTradeAction($"Error closing order: {ex.Message}")
            Throw
        End Try
    End Function
    Public Async Function UpdateStopLossAsync(dealId As String, stopLevel As Decimal) As Task(Of JObject)
        Try
            ' Define the endpoint for updating the stop loss of the position
            Dim endpoint As String = $"/positions/{dealId}"

            ' Create the payload with the new stop level
            Dim payload As New With {
            .stopLevel = stopLevel
        }

            ' Serialize the payload to JSON
            Dim jsonPayload As String = JsonConvert.SerializeObject(payload)
            Dim content As New StringContent(jsonPayload, Encoding.UTF8, "application/json")

            ' Set security headers
            SetSecurityHeaders(GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)

            ' Make the PUT request to update the stop level
            Dim response As HttpResponseMessage = Await client.PutAsync(GlobalVariables.BASE_URL & endpoint, content)

            ' Read the API response content
            Dim responseContent As String = Await response.Content.ReadAsStringAsync()

            ' Ensure the request was successful
            response.EnsureSuccessStatusCode()

            ' Parse and return the API response as a JObject
            Dim jsonResponse As JObject = JObject.Parse(responseContent)
            Return jsonResponse

        Catch ex As Exception
            mainForm.LogTradeAction($"Error updating stop loss: {ex.Message}")
            Throw
        End Try
    End Function


    Public Async Function FetchTradeHistoryAsync() As Task(Of String)
        Try
            Dim toDate As String = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss")
            Dim fromDate As String = DateTime.UtcNow.AddDays(-7).ToString("yyyy-MM-ddTHH:mm:ss")

            Dim endpoint As String = $"/history/transactions?from={fromDate}&to={toDate}&type=TRADE"
            Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
            response.EnsureSuccessStatusCode()

            Return Await response.Content.ReadAsStringAsync()
        Catch ex As Exception
            mainForm.LogTradeAction($"Error fetching trade history: {ex.Message}")
            Return String.Empty
        End Try
    End Function

    Private Async Function PostAsync(url As String, payload As Object, securityToken As String, cstToken As String) As Task(Of HttpResponseMessage)
        Dim attempts As Integer = 0
        Dim maxRetries As Integer = 5
        Dim delayBetweenRetries As Integer = 1000
        Dim lastException As Exception = Nothing

        While attempts < maxRetries
            Try
                attempts += 1
                SetSecurityHeaders(securityToken, cstToken)
                Dim jsonPayload As String = JsonConvert.SerializeObject(payload)
                Dim content As New StringContent(jsonPayload, Encoding.UTF8, "application/json")
                Return Await client.PostAsync(url, content)

            Catch ex As Exception
                lastException = ex
                mainForm.LogTradeAction($"Error during POST request to {url} on attempt {attempts}: {ex.Message}")
                If attempts >= maxRetries Then
                    Exit While
                End If
            End Try

            Await Task.Delay(delayBetweenRetries)
        End While

        Return Nothing
    End Function

    Private Async Function DeleteAsync(url As String, securityToken As String, cstToken As String) As Task(Of HttpResponseMessage)
        Dim attempts As Integer = 0
        Dim maxRetries As Integer = 5
        Dim delayBetweenRetries As Integer = 1000
        Dim lastException As Exception = Nothing

        While attempts < maxRetries
            Try
                attempts += 1
                SetSecurityHeaders(securityToken, cstToken)
                Return Await client.DeleteAsync(url)

            Catch ex As Exception
                lastException = ex
                mainForm.LogTradeAction($"Error during DELETE request to {url} on attempt {attempts}: {ex.Message}")
                If attempts >= maxRetries Then
                    Exit While
                End If
            End Try

            Await Task.Delay(delayBetweenRetries)
        End While

        Return Nothing
    End Function

    Private Async Function GetAsync(url As String, securityToken As String, cstToken As String) As Task(Of HttpResponseMessage)
        Dim attempts As Integer = 0
        Dim maxRetries As Integer = 5
        Dim delayBetweenRetries As Integer = 1000
        Dim lastException As Exception = Nothing

        While attempts < maxRetries
            Try
                attempts += 1
                SetSecurityHeaders(securityToken, cstToken)
                Return Await client.GetAsync(url)

            Catch ex As Exception
                lastException = ex
                mainForm.LogTradeAction($"Error during GET request to {url} on attempt {attempts}: {ex.Message}")
                If attempts >= maxRetries Then
                    Exit While
                End If
            End Try

            Await Task.Delay(delayBetweenRetries)
        End While

        Return Nothing
    End Function

    Private Sub SetSecurityHeaders(securityToken As String, cstToken As String)
        client.DefaultRequestHeaders.Remove("X-SECURITY-TOKEN")
        client.DefaultRequestHeaders.Remove("CST")
        If Not String.IsNullOrEmpty(securityToken) Then
            client.DefaultRequestHeaders.Add("X-SECURITY-TOKEN", securityToken)
        End If
        If Not String.IsNullOrEmpty(cstToken) Then
            client.DefaultRequestHeaders.Add("CST", cstToken)
        End If
    End Sub

    Public Async Function FetchAllInstrumentsAsync() As Task(Of String)
        Try
            Dim endpoint As String = "/marketnavigation/hierarchy_v1.crypto_currencies_group"
            Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
            response.EnsureSuccessStatusCode()

            Dim responseData As String = Await response.Content.ReadAsStringAsync()
            Dim json As JObject = JObject.Parse(responseData)
            Dim instrumentDetails As New StringBuilder()

            ' Check for nested nodes
            If json("nodes") IsNot Nothing Then
                For Each node As JObject In json("nodes")
                    If node("id") IsNot Nothing Then
                        Dim nodeId As String = node("id").ToString()
                        Dim subNodeData As String = Await FetchInstrumentsFromNodeAsync(nodeId)
                        instrumentDetails.AppendLine(subNodeData)
                    Else
                        mainForm.LogTradeAction("Node ID is missing.")
                    End If
                Next
            End If

            ' Check for markets in the current node
            If json("markets") IsNot Nothing Then
                For Each market As JObject In json("markets")
                    If market("epic") IsNot Nothing AndAlso market("name") IsNot Nothing Then
                        Dim epic As String = market("epic").ToString()
                        Dim name As String = market("name").ToString()
                        instrumentDetails.AppendLine($"Epic: {epic}, Name: {name}")
                    End If
                Next
            End If

            ' Log the instrument details
            mainForm.LogTradeAction($"Fetched instrument details: {instrumentDetails.ToString()}")
            Return instrumentDetails.ToString()

        Catch ex As Exception
            mainForm.LogTradeAction($"Error in FetchAllInstrumentsAsync: {ex.Message}")
            Throw
        End Try
    End Function
    Private Async Function FetchInstrumentsFromNodeAsync(nodeId As String) As Task(Of String)
        If String.IsNullOrEmpty(nodeId) Then
            Return "Node ID is empty or null."
        End If

        Dim endpoint As String = $"/marketnavigation/{nodeId}"
        Try
            Dim response As HttpResponseMessage = Await GetAsync(GlobalVariables.BASE_URL & endpoint, GlobalVariables.SECURITY_TOKEN, GlobalVariables.CST_TOKEN)
            response.EnsureSuccessStatusCode()

            Dim responseData As String = Await response.Content.ReadAsStringAsync()
            Dim json As JObject = JObject.Parse(responseData)
            Dim instrumentDetails As New StringBuilder()

            ' Check for markets
            If json("markets") IsNot Nothing Then
                For Each market As JObject In json("markets")
                    If market("epic") IsNot Nothing AndAlso market("name") IsNot Nothing Then
                        Dim epic As String = market("epic").ToString()
                        Dim name As String = market("name").ToString()
                        instrumentDetails.AppendLine($"Epic: {epic}, Name: {name}")
                    End If
                Next
            End If

            Return instrumentDetails.ToString()

        Catch ex As Exception
            mainForm.LogTradeAction($"Error in FetchInstrumentsFromNodeAsync for Node {nodeId}: {ex.Message}")
            Throw
        End Try
    End Function






End Class
