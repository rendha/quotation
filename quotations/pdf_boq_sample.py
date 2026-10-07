"""
The 19 BOQ rows of the Dehlsen sample quotation.

Only these rows are printed on page 3.  For every row:
  keywords / exclude : words looked for in a quotation item's *description* to find "its" item
  spec               : sample specification text ("\n" = new line)
  qty, make          : sample values, used when the quotation has no matching item
Quantity and make come from the matching item when there is one (they change with the
selections made on the quotation page).
"""

SAMPLE_BOQ = [
    dict(sr=1, particular="PV Module", keywords=["MODULE"], exclude=["CLEAN"],
         spec="N- Type TOPCon 600-620 WP High performance bifacial solar module 132 half-cell, glass/glass, "
              "N-Type TOPCon, 12 years Manufacturer's warranty and 30 years Performance guarantee",
         qty="", make="ADANI"),
    dict(sr=2, particular="Inverter", keywords=["INVERTER"], exclude=["CABLE", "WIRE"],
         spec="{kw} KW {phase} phase on grid inverter, 1 MPPT trackers, efficiency up to 98.3%, Type II DC/AC SPD, Wi- Fi\n"
              "Warranty: 8 Years",
         qty="1", make="POLYCAB"),
    dict(sr=3, particular="PV Mounting Structure", keywords=["STRUCTURE", "MOUNTING"], exclude=[],
         spec="RCC Roof Structure: Welded Structure using GI pipe with Suitable section as per site condition\n"
              "Height: 1.2M\nGauge: 16\nClamps: Aluminum 6063 Anodized\n"
              "Fasteners: 8x65 SS Bolt with M8 Nut and Spring Washer\nPrimer: Grey 1 Coat\n"
              "Anchor Bolt: 4\u201d 8mm Bedge Anchor Bolt\nAnchoring Method: Chemical Anchoring \u2013 Forsoc\n"
              "Grout: Conbextra GP2 \u2013 Forsoc/ CONCREATE",
         qty="1", make="REPUTED"),
    dict(sr=4, particular="Walkway", keywords=["WALKWAY"], exclude=[],
         spec="3x1 GP Pipe/ FRP Molded grating walkway 310mm", qty="1", make="-"),
    dict(sr=5, particular="DCDB", keywords=["DCDB"], exclude=["CABLE", "WIRE"],
         spec="DCDB 1 IN 1 OUT: +Ve Fuse Holder, -Ve Terminal Connector with DC SPD: Type II, 600V,40kA per string, "
              "IP67 Poly carbonate enclosure",
         qty="1", make="L&K, ELMEX"),
    dict(sr=6, particular="ACDB", keywords=["ACDB"], exclude=["CABLE", "WIRE"],
         spec="1 in 1 out: Input Terminal Connector\nOutput: 32A, 2P,MCB\nSPD: Type II SPD\nEnclosure: Poly carbonate enclosure",
         qty="1", make="L&K, ELMEX"),
    dict(sr=7, particular="DC Cable", keywords=["DC CABLE", "DC WIRE"], exclude=[],
         spec="4 Sq.mm 1.8kV XLPO Type 1, Flexible Annealed Tinned Copper conductor1C X 4 Sq.mm Solar Flexible ATC "
              "Conductor, Ebeam Crossed Linked LSOH Insulated, 120 deg C max Temp",
         qty="50", make="POLYCAB/APAR"),
    dict(sr=8, particular="AC LT Cable\nInverter to ACDB", keywords=["AC WIRE", "FR COPPER", "INVERTER TO ACDB"], exclude=[],
         spec="2RX4 Sq.mm FRLS Flexible Copper wire", qty="20", make="VGUARD/FINOLEX"),
    dict(sr=9, particular="AC LT Cable\nACDB to Metering Panel",
         keywords=["ACDB TO", "UG CABLE", "AC CABLE", "LT CABLE"], exclude=[],
         spec="2CX6 Sq.mm XLPE, Aluminum Ug Cable", qty="30", make="POLYCAB/KEI"),
    dict(sr=10, particular="Metering Panel", keywords=["METERING PANEL", "METER PANEL"], exclude=["CABLE"],
         spec="Vermin Proof GI Powder Coated Enclosure, UV protected Weld free Manufacturing Process, Compliance to "
              "IEC 60529 with Breaker compartment and Provision for Single phase Energy Meter",
         qty="1", make="EXCEL EARTHING"),
    dict(sr=11, particular="Lightning Arrester", keywords=["LIGHTNING", "ARREST"], exclude=[],
         spec="Vertical Air Terminal with accessories 1m", qty="1", make="EXCEL EARTHING"),
    dict(sr=12, particular="Earthing", keywords=["EARTH"], exclude=[],
         spec="DC Side: 25 Sq.mm AL Wire\nAC Side: 25 Sq.mm AL Wire\nLA Side: 25 Sq.mm AL Wire\n"
              "14 mm copper bonded rod-3\n10 SWG Copper Conductor for Below Ground level",
         qty="3", make="EXCEL EARTHING"),
    dict(sr=13, particular="Cable Accessories", keywords=["ACCESSOR", "LUG", "GLAND"], exclude=[],
         spec="Lugs, Gland", qty="", make="DOWELL'S"),
    dict(sr=14, particular="Conduits", keywords=["CONDUIT"], exclude=[],
         spec="25mm PVC Ivory conduit With GI Saddle", qty="", make="FINOLEX/GEO/ PRECISION"),
    dict(sr=15, particular="Net Meter", keywords=["NET METER"], exclude=[],
         spec="CL:1 LT TOD Tested from KSEB/ Electrical inspectorate", qty="", make="L&K"),
    dict(sr=16, particular="Energy Meter", keywords=["ENERGY METER"], exclude=[],
         spec="CL: 1 LT TOD Tested from KSEB/ Electrical inspectorate", qty="1", make="L&K"),
    dict(sr=17, particular="Documentation", keywords=["DOCUMENT"], exclude=[],
         spec="CEIG Approval & KSEB and Inspectorate Interaction for The Entire Plant, Termination to The KSEB Grid and "
              "Synchronization, all fee related to electrical inspectorate included in the quotation.",
         qty="1", make="DEHLSEN"),
    dict(sr=18, particular="Design", keywords=["DESIGN"], exclude=[],
         spec="Design And Engineering of Solar Power Plant with Energy Yield, Design Calculations+ Site Survey and "
              "Other Misc. Activities.",
         qty="1", make="DEHLSEN"),
    dict(sr=19, particular="AMC", keywords=["AMC"], exclude=[],
         spec="AMC: 5 years For the Workmanship and BOS\nTAT: 2 Working Days From the date of Reg. Complaint\n"
              "Module Cleaning: First 1 cleaning free upon installation, Paid Cleaning 700 Per Visit",
         qty="1", make="DEHLSEN"),
]

