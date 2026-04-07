import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

#Konstanten +++++++++++++++++++++++++++++++++++++++++++++++++++++++++
delta_t = 300 #sekunden
#Gebäude
R_building = 0.014
C_building = 5e7 
T_soll = 20
#Wärmepumpe
a = 3.5
b = -0.1
Q_wp_max = 10000.0
#Thermischer Speicher
E_th_max = 7000.0
Q_store_max = 10000.0
#Batteriespeicher
E_bat_max = 10000.0
P_bat_max = 5000.0
#PV-Anlage
PV_efficiency = 0.2
A_pv = 100
#Preisdefinitionen (Preisgrenzen) in €/kWh
price_low = 0.02
price_high = 0.055 


#Daten aus CSV auslesen ++++++++++++++++++++++++++++++++++++++++++++++
data = pd.read_csv("Daten_hackathon.csv")       
n = len(data)       
timestamp = data.iloc[:, 0].to_numpy()          #Timestamp aus CSV                           
GHI = data.iloc[:, 2].to_numpy()                #GHI Strahlung für PV in W/m²          
T_out = data.iloc[:, 3].to_numpy()              #Aussentemperatur in °C           
Q_solarthermie = data.iloc[:, 4].to_numpy()     #Solarthermie-Erzeugung in W                   
Price = data.iloc[:, 5].to_numpy()              #Strompreis in €/kWh           
P_demand = data.iloc[:, 6].to_numpy()        #elektrischer Bedarf in W           
Q_demand = data.iloc[:, 7].to_numpy()        #aktueller thermischer Bedarf in W           

#Berechnung
T_in = np.zeros(n); T_in[0] = 20    #Startwert 20°C
E_th = np.zeros(n+1); E_th[0] = 3500                         #Startwert 3500 Wh
E_bat = np.zeros(n+1);E_bat[0] = 5000                        #Startwert 5000 Wh

Q_wp =0
P_wp=0
Q_heat=0
Q_store=0
P_pv=0
P_bat=0
delta_T_in=0

P_buy=0
Cost=0

P_sum_load=0
P_sum_buy=0
E_pv=0
E_sum_pv=0

kp=0.1
e_temp=0
u_temp=0

f_wp=np.zeros(4)            #Faktor, wieviel % von der benötigten Wärmeleistung die WP laufen soll --> rest aus speicher
f_store_th=np.zeros(4)      #Faktor, wieviel % von der max. leistung in den Speicher die WP zusätzlich läuft, um Speicher zu füllen

f_bat_use=np.zeros(6)        #Faktor, wieviel % von der benötigten el-Leistung aus der Batterie gezogen wird.
f_bat_sell=np.zeros(6)       #Faktor, wieviel % von der max.Leistung der Batterie zusätlich die Betterie geladen/entladen werden soll.

for i in range(n):

    #Berechnung Außeneinflüsse
    P_pv=GHI[i]*A_pv*PV_efficiency
    E_pv=(P_pv/1000)*(delta_t/3600)
    E_sum_pv+=E_pv
    COP = a-b*T_out[i]
    
    #Berechnung Speicherstand in Prozent
    E_bat_pct = E_bat[i]/E_bat_max
    E_th_pct = E_th[i]/E_th_max

    #Temp. regelung mit P-Regler
    e_temp=T_soll - T_in[i]
    u_temp=kp*e_temp
    if(u_temp<0): u_temp=0
    Q_heat=u_temp*Q_store_max

    #Berrechnung benötigte Wärmeleistung --> die Heizleistung - Leistung der Solarthermie 
    Q_needed=Q_heat-Q_solarthermie[i]

    # Einstellung der Faktoren für Wärmepumpe, Speicher und Batterie, je nach Strompreis
    match Price[i]:
        case x if x < 0:
            f_wp[0]=1
            f_wp[1]=1
            f_wp[2]=1
            f_wp[3]=1   

            f_store_th[0]=0
            f_store_th[1]=1
            f_store_th[2]=1
            f_store_th[3]=1    

            f_bat_use[0]=0
            f_bat_use[1]=0
            f_bat_use[2]=0
            f_bat_use[3]=0
            f_bat_use[4]=0
            f_bat_use[5]=0

            f_bat_sell[0]=0
            f_bat_sell[1]=-0.1
            f_bat_sell[2]=-0.5
            f_bat_sell[3]=-1
            f_bat_sell[4]=-1
            f_bat_sell[5]=-1
        case x if x < price_low:
            f_wp[0]=0.5
            f_wp[1]=0.75
            f_wp[2]=1
            f_wp[3]=1   

            f_store_th[0]=0
            f_store_th[1]=0.05
            f_store_th[2]=0.1
            f_store_th[3]=0.2

            f_bat_use[0]=1
            f_bat_use[1]=1
            f_bat_use[2]=0.5
            f_bat_use[3]=0
            f_bat_use[4]=0
            f_bat_use[5]=0

            f_bat_sell[0]=0.1
            f_bat_sell[1]=0.1
            f_bat_sell[2]=0
            f_bat_sell[3]=0
            f_bat_sell[4]=-0.1
            f_bat_sell[5]=-0.2
        case x if x < price_high:
            f_wp[0]=0.25
            f_wp[1]=0.5
            f_wp[2]=0.75
            f_wp[3]=1   

            f_store_th[0]=0
            f_store_th[1]=0
            f_store_th[2]=0
            f_store_th[3]=0.1

            f_bat_use[0]=1
            f_bat_use[1]=1
            f_bat_use[2]=0.75
            f_bat_use[3]=0.5
            f_bat_use[4]=0.25
            f_bat_use[5]=0

            f_bat_sell[0]=0.2
            f_bat_sell[1]=0.2
            f_bat_sell[2]=0.1
            f_bat_sell[3]=0
            f_bat_sell[4]=0
            f_bat_sell[5]=0
        case _:
            f_wp[0]=0
            f_wp[1]=0.25
            f_wp[2]=0.5
            f_wp[3]=0.75   

            f_store_th[0]=0
            f_store_th[1]=0
            f_store_th[2]=0
            f_store_th[3]=0

            f_bat_use[0]=1
            f_bat_use[1]=1
            f_bat_use[2]=1
            f_bat_use[3]=0.75
            f_bat_use[4]=0.5
            f_bat_use[5]=0.25

            f_bat_sell[0]=0.3
            f_bat_sell[1]=0.3
            f_bat_sell[2]=0.2
            f_bat_sell[3]=0.1
            f_bat_sell[4]=0
            f_bat_sell[5]=0

    # Einstellung der Wärmepumpe und des Bezugs aus dem thermischen Speicher mit den eingestellten Faktoren (je nach Speicherstand)      
    if Q_needed > 0:
        match E_th_pct:
            case x if x >0.8:
                Q_wp= min((f_wp[0]*Q_needed + f_store_th[0]*Q_store_max),Q_wp_max)
                Q_store= Q_needed-Q_wp
            case x if x >0.5:
                Q_wp= min((f_wp[1]*Q_needed + f_store_th[1]*Q_store_max),Q_wp_max)
                Q_store= Q_needed-Q_wp
            case x if x >0.2:
                Q_wp= min((f_wp[2]*Q_needed + f_store_th[2]*Q_store_max),Q_wp_max)
                Q_store= Q_needed-Q_wp
            case x if x >0.005:
                Q_wp= min((f_wp[3]*Q_needed + f_store_th[3]*Q_store_max),Q_wp_max)
                Q_store= Q_needed-Q_wp
            case _:
                Q_wp=Q_needed
                Q_store=0
    elif E_th_pct<1:
        if E_th_pct<0.8:
            Q_wp=0.1*Q_store_max 
        else: Q_wp=0   
        Q_store=Q_needed-Q_wp
    else:     
        Q_wp=0
        # Was passiert, wenn Speicher voll und überschüssige Wärme????????

    #Berechnung des neuen thermischen Speicherstandes
    E_th[i+1]=E_th[i]-(Q_store*(delta_t/3600))
    #Berechnung der el. Leistung der Wärmepumpe
    P_wp=Q_wp/COP
    #Berrechnung benötigte el.Leistung --> Leistung Wärmepumpe- PV Leistung
    P_needed=P_demand[i]+P_wp-P_pv

    # Einstellung des Bezugs aus der Batterie (laden oder entladen) und ob Strom gekauft oder verkauft wird (negativ = verkaufen)
    if P_needed > 0:
        match E_bat_pct:
            case x if x >0.999:
                P_bat= min((f_bat_use[0]*P_needed + f_bat_sell[0]*P_bat_max),P_bat_max)
                P_buy= P_needed-P_bat

            case x if x >0.9:
                P_bat= min((f_bat_use[1]*P_needed + f_bat_sell[1]*P_bat_max),P_bat_max)
                P_buy= P_needed-P_bat
                 
            case x if x >0.6:
                P_bat= min((f_bat_use[2]*P_needed + f_bat_sell[2]*P_bat_max),P_bat_max)
                P_buy= P_needed-P_bat
                
            case x if x >0.3:
                P_bat= min((f_bat_use[3]*P_needed + f_bat_sell[3]*P_bat_max),P_bat_max)
                P_buy= P_needed-P_bat
                
            case x if x >0.1:
                P_bat= min((f_bat_use[4]*P_needed + f_bat_sell[4]*P_bat_max),P_bat_max)
                P_buy= P_needed-P_bat
                
            case x if x >0.005:
                P_bat= min((f_bat_use[5]*P_needed + f_bat_sell[5]*P_bat_max),P_bat_max)
                P_buy= P_needed-P_bat

            case _:
                P_bat= 0
                P_buy= P_needed

    else:
        if E_bat_pct<0.99:
            P_bat=P_needed
            P_buy=0
        else:     
            P_bat=0
            P_buy=P_needed
        # Was passiert, wenn Speicher voll und überschüssige Strom????????

    #Berrechnung des neuen Batteriestandes
    E_bat[i+1]=E_bat[i]-(P_bat*(delta_t/3600))

    #InnenTemp. berechnen
    if(i<(n-1)):
        delta_T_in= (((T_out[i]-T_in[i])/R_building)+Q_heat)*(delta_t/C_building)
        T_in[i+1]=T_in[i]+delta_T_in    
    
    #Kosten aufsummieren --> negativ=gewinn
    Cost+=(P_buy/1000)*(delta_t/3600)*Price[i]

    P_sum_load+=P_demand[i]+P_wp
    if P_buy>0:
        P_sum_buy+=P_buy
    

   # print(round(T_in[i],3), end="   ")
    #print(i, end=" ")
    #print(round(Cost,3), end="   ")
   # print(round(Price[i],3), end="   ")
   # print(round(P_buy,3), end="   ")
   # print(round(P_pv,3), end="   ")
    #print(round(P_needed,3), end="   ")
    #print(round(E_bat_pct,4), end="   ")
    #print(round(E_th_pct,2), end="   ")
   # print(round(Q_heat,3))


autarkie=((P_sum_load-P_sum_buy)/P_sum_load)*100
print(f"Autarkie:      {autarkie:10.3f} %")
print(f"Gewinn:        {-Cost:10.3f} €")
print(f"PV-Erzeugung:  {E_sum_pv:10.3f} kWh")





    




