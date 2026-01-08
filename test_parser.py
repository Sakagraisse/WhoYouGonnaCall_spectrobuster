
import os

def parse_file():
    content = """Reading	X	Y	Z	L*	a*	b*	380.000	390.000	400.000	410.000	420.000	430.000	440.000	450.000	460.000	470.000	480.000	490.000	500.000	510.000	520.000	530.000	540.000	550.000	560.000	570.000	580.000	590.000	600.000	610.000	620.000	630.000	640.000	650.000	660.000	670.000	680.000	690.000	700.000	710.000	720.000	730.000
1	202.003710	179.404783	57.243948	124.951379	32.235351	65.952274	0.00441786	0.00403514	0.00360195	0.018642	0.0640588	0.166098	0.438224	1.07973	1.38008	0.99481	0.760106	0.824125	1.12056	1.46595	1.68165	1.81362	1.96521	2.17971	2.43902	2.71537	2.91392	2.9853	3.06579	4.10474	3.97825	5.73143	3.9209	1.99835	1.25193	0.884711	0.63886	0.462007	0.342776	0.254453	0.187821	0.141066
"""
    lines = content.strip().split('\n')
    
    header_fields = []
    data_values = []
    
    is_simple_tabular = False
    if len(lines) >= 2:
        first_line_parts = lines[0].strip().split()
        print(f"First line parts: {first_line_parts[:10]}...")
        
        wavelength_headers = []
        for part in first_line_parts:
            try:
                wl = float(part)
                if 300 <= wl <= 800:
                    wavelength_headers.append(wl)
            except ValueError:
                pass
        
        print(f"Found {len(wavelength_headers)} wavelength headers")
        
        if len(wavelength_headers) > 10:
            is_simple_tabular = True
            header_fields = first_line_parts
            for line in reversed(lines[1:]):
                if line.strip():
                    data_values = line.strip().split()
                    break
    
    print(f"Is Simple Tabular: {is_simple_tabular}")
    
    longueur_onde = []
    intensité = []

    if is_simple_tabular:
        for idx, field in enumerate(header_fields):
            try:
                wl = float(field)
                if 300 <= wl <= 830 and idx < len(data_values):
                    val = float(data_values[idx])
                    longueur_onde.append(wl)
                    intensité.append(val)
            except ValueError:
                pass
    
    print(f"Extracted {len(longueur_onde)} points")
    if len(longueur_onde) > 0:
        print(f"First point: {longueur_onde[0]} nm, {intensité[0]}")
        print(f"Last point: {longueur_onde[-1]} nm, {intensité[-1]}")

parse_file()
