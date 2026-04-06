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
E_th = np.zeros(n); E_th[0] = 3500                         #Startwert 3500 Wh
E_bat = np.zeros(n);E_bat[0] = 5000                        #Startwert 5000 Wh

Q_wp =0
P_wp=0
Q_heat=0
Q_store=0
P_pv=0
P_bat=0
delta_T_in=0

P_buy=0

kp=0.1
e_temp=0
u_temp=0

f_wp=np.zeros(4)
f_store_th=np.zeros(4)
f_bat=np.zeros(4)

for i in range(2000):

    #Berechnung Außeneinflüsse
    P_pv=GHI[i]*A_pv*PV_efficiency
    COP = a-b*T_out[i]
    
    #Berechnung Speicherstand in Prozent
    E_bat_pct = E_bat[i]/E_bat_max
    E_th_pct = E_th[i]/E_th_max

    #Temp. regelung mit P-Regler
    e_temp=T_soll - T_in[i]
    u_temp=kp*e_temp
    if(u_temp<0): u_temp=0
    Q_heat=u_temp*Q_store_max

    Q_needed=Q_heat-Q_solarthermie[i]

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
        case x if x < price_low:
            f_wp[0]=0.5
            f_wp[1]=0.75
            f_wp[2]=1
            f_wp[3]=1   

            f_store_th[0]=0
            f_store_th[1]=0.05
            f_store_th[2]=0.1
            f_store_th[3]=0.2
        case x if x < price_high:
            f_wp[0]=0.25
            f_wp[1]=0.5
            f_wp[2]=0.75
            f_wp[3]=1   

            f_store_th[0]=0
            f_store_th[1]=0
            f_store_th[2]=0
            f_store_th[3]=0.1
        case _:
            f_wp[0]=0
            f_wp[1]=0.25
            f_wp[2]=0.5
            f_wp[3]=0.75   

            f_store_th[0]=0
            f_store_th[1]=0
            f_store_th[2]=0
            f_store_th[3]=0
          
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

    E_th[i+1]=E_th[i]-(Q_store*(delta_t/3600))
    P_wp=Q_wp/COP

    P_needed=P_demand[i]+P_wp-P_pv

    if P_needed > 0:
        match E_bat_pct:
            case x if x >0.8:
                P_bat= f_bat[0]*P_bat_max
                P_buy= P_needed-P_bat
                
                Q_wp= min((f_wp[0]*Q_needed + f_store_th[0]*Q_store_max),Q_wp_max)
                P_bat= P_needed-Q_wp
            
            
            case x if x >0.5:
                
            case x if x >0.2:
                
            case x if x >0.005:
                
            case _:
                Q_wp=Q_needed
                Q_store=0
    elif E_bat_pct<1:
        if E_bat_pct<0.8:
            Q_wp=0.1*Q_store_max 
        else: Q_wp=0   
        Q_store=Q_needed-Q_wp
    else:     
        Q_wp=0
        # Was passiert, wenn Speicher voll und überschüssige Wärme????????


    E_bat[i+1]=E_bat[i]-(P_bat*(delta_t/3600))


    #InnenTemp. berechnen
    if(i<(n-1)):
        delta_T_in= (((T_out[i]-T_in[i])/R_building)+Q_heat)*(delta_t/C_building)
        T_in[i+1]=T_in[i]+delta_T_in    
    

    print(round(T_in[i],3), end="   ")
    #print(i, end=" ")
    
    print(round(P_pv,3), end="   ")
    print(round(P_needed,3), end="   ")
    print(round(E_bat_pct,2), end="   ")
    print(round(E_th_pct,2), end="   ")
    print(round(Q_heat,3))

    

    





    




