# Server configuration for TestDaemon world

# Only trinst has a Godot client map so far, so it is the only zone the cluster
# hosts. kauldur (the Masters of Darkness start zone) has no map yet; re-add it
# here (and to STATICZONES) once its Godot scene exists, otherwise the server
# wastes CPU simming a zone no client can render.
CLUSTERNAMES = [
("trinst",),
]

WORLDPORT = 2008
ZONESTARTPORT = 2010
PLAYERPASSWORD = "mmo"
MAXPLAYERS = 64
STATICZONES = ["trinst"]

REBOOT = True
REBOOT_HOUR = 3
REBOOT_MINUTE = 0
