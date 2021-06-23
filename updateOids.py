import os

inTCADs = arcpy.GetParameterAsText(0)
inModals = arcpy.GetParameterAsText(1)
inModalFld = arcpy.GetParameterAsText(2)

desc = arcpy.Describe(inTCADs)
fids = desc.FIDset.split(";") 

oid = 0
if len(fids) != 1:
	arcpy.AddError("Select 1 feature in {}".format(inTCADs))
	sys.exit(0)
else:
	oid = int(fids[0])

arcpy.AddMessage("Adding Oids {} to {}".format(oid, inModals))

desc = arcpy.Describe(inModals)
if len(desc.FIDset.split(";")) < 1:
	arcpy.AddError("Select 1+ features in {}".format(inModals))
	sys.exit(0)

arcpy.management.CalculateField(inModals, inModalFld, oid, "PYTHON3", '', "TEXT")

logfile = os.path.join(arcpy.env.scratchFolder, 'updateOidLog.txt')
arcpy.AddMessage("Adding info to {}".format(logfile))

fids = desc.FIDset.split(";")

f = open(logfile, "a")
for fid in fids:
	f.write("{},{}\n".format(fid, oid))

f.close()