// MT5 Market Data Publisher - read-only; does not place trades.
#property strict
#property version "1.00"
input string InpIngestURL = "https://YOUR-DOMAIN.example/api/v1/ingest";
input string InpApiToken = "CHANGE-THIS-TO-A-LONG-RANDOM-TOKEN";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M5;
input int InpBarsToSend = 300;
input int InpTimerSeconds = 5;

string TfName(ENUM_TIMEFRAMES tf)
{
   switch(tf) {
      case PERIOD_M1: return "M1";
      case PERIOD_M5: return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1: return "H1";
      case PERIOD_H4: return "H4";
      default: return EnumToString(tf);
   }
}
string Num(double value) { return DoubleToString(value, _Digits); }

int OnInit()
{
   if(StringFind(InpIngestURL, "https://") != 0 || InpApiToken == "" ||
      StringFind(InpApiToken, "CHANGE-") == 0) return INIT_PARAMETERS_INCORRECT;
   if(!SymbolSelect(_Symbol, true)) return INIT_FAILED;
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("MT5 data publisher started: ", _Symbol, " ", TfName(InpTimeframe));
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) { Print("Tick read failed: ", GetLastError()); return; }
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(_Symbol, InpTimeframe, 0, MathMax(30, MathMin(InpBarsToSend, 2000)), rates);
   if(copied < 20) { Print("Not enough bars: ", copied); return; }

   string body = "{\"symbol\":\"" + _Symbol + "\",";
   body += "\"timeframe\":\"" + TfName(InpTimeframe) + "\",";
   body += "\"bid\":" + Num(tick.bid) + ",\"ask\":" + Num(tick.ask) + ",";
   body += "\"timestamp_utc\":" + IntegerToString((long)tick.time) + ",\"bars\":[";
   for(int i=0; i<copied; i++) {
      if(i > 0) body += ",";
      body += "{\"time\":" + IntegerToString((long)rates[i].time);
      body += ",\"open\":" + Num(rates[i].open) + ",\"high\":" + Num(rates[i].high);
      body += ",\"low\":" + Num(rates[i].low) + ",\"close\":" + Num(rates[i].close);
      body += ",\"tick_volume\":" + IntegerToString((long)rates[i].tick_volume) + "}";
   }
   body += "]}";

   char request[], response[];
   string response_headers;
   int n = StringToCharArray(body, request, 0, WHOLE_ARRAY, CP_UTF8);
   if(n > 0) ArrayResize(request, n - 1);
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + InpApiToken + "\r\n";
   ResetLastError();
   int status = WebRequest("POST", InpIngestURL, headers, 8000, request, response, response_headers);
   if(status == 200) Print("Bridge update OK: ", _Symbol, " bars=", copied);
   else Print("Bridge upload failed. HTTP=", status, " error=", GetLastError(), " response=", CharArrayToString(response));
}
