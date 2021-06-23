def getMsgs(startMsg):
    msgCnt = arcpy.GetMessageCount()
    msg=arcpy.GetMessage(msgCnt-1)
    arcpy.AddMessage("{} {}".format(startMsg,msg))


def cleanUp(layer):
    d = arcpy.Describe(layer)
    datasetPath = d.catalogpath
    if arcpy.Exists(datasetPath):
        arcpy.management.Delete(datasetPath)
        getMsgs("Deleted {}".format(datasetPath))
    else:
        arcpy.AddMessage("{} does not exist".format(datasetPath))


def doErase(inFeatures, eraseFeatures, eraseFcName):
    result = arcpy.analysis.Erase(inFeatures, eraseFeatures, eraseFcName, None)
    erasedOutputs = result.getOutput(0)
    getMsgs("Erased {} from {} to generate {}".format(inFeatures, eraseFeatures, erasedOutputs))
    return erasedOutputs


def doBuffer(inFeatures, bufferedFeatures, bufferDistance):
    result = arcpy.analysis.Buffer(inFeatures, bufferedFeatures, bufferDistance, "FULL", "ROUND", "NONE", None, "PLANAR")
    getMsgs("Buffered {} by {} to generate {}".format(inFeatures, bufferDistance, bufferedFeatures))
    return result.getOutput(0)

def intersectToPoints(inLayers, outLayer):
    result = arcpy.analysis.Intersect(inLayers, outLayer, "ONLY_FID", None, "POINT")
    getMsgs("Intersected {} and {}".format(inLayers[0], inLayers[1]))
    return result.getOutput(0)

def dropFields(layer, fields):
    arcpy.management.DeleteField(layer,fields)
    getMsgs("Deleted fields {} from {}".format(fields, layer))

def dissolveFeatures(inLayer, outLayerName):
    result = arcpy.management.Dissolve(inLayer, outLayerName, None, None, "SINGLE_PART", "DISSOLVE_LINES")
    outLayer = result.getOutput(0)
    getMsgs("Dissolved {} into {}".format(inLayer,outLayer))
    return outLayer


inTCadLyr = arcpy.GetParameterAsText(0)
inTCadBuffDistance = arcpy.GetParameterAsText(1)
inModalCompLyr = arcpy.GetParameterAsText(2)
matchOption = arcpy.GetParameterAsText(3)
preserveDerivativeData = arcpy.GetParameter(4)
clipLength = arcpy.GetParameterAsText(5)
renameField = arcpy.GetParameterAsText(6)
renameFldAlias = arcpy.GetParameterAsText(7)
modal_comp_out = arcpy.GetParameterAsText(8) ##modal_composite_03_tcadOid

arcpy.AddMessage("matchOption is set to {}".format(matchOption))
arcpy.AddMessage("preserveDerivativeData is set to {}".format(preserveDerivativeData))

BUFFERED_TCAD="intermediateBufferedTCAD"
#ERASE_RCL = "intermediateEraseRCLs"
ERASE_INTERSECTIONS = "intermediateErasedInts"
INTERSECTED_LYRS = "intermediateIntersections"
INTERSECTED_MODALS = "intermediateModalIntersections"
BUFFERED_INTERSECTIONS = "intermediateBufferedIntersections"
SEGS_S_JOIN_TCAD = "intermediateSegsWithTCAD"
OUT_MODAL_JOINED_LYR = modal_comp_out ##"modal_composite_03_tcadOid"
FREQ_SEGID_TCADOID = "intermediateFreqSegsWithTCADOids"
CADBUF_ERASE_MODAL = "intermediateErasedInts_Clip"
DISSOLVED_FEATS_01 = 'intermediateDissolvedIntersections01'
DISSOLVED_FEATS_02 = 'intermediateDissolvedIntersections02'
MERGE_INTS = 'intermediateMergedIntersections'


buffDist = "{} Feet".format(inTCadBuffDistance)

## intersect the input transcad data w/the modal composite layer to create intersection points
intersectionPoints = intersectToPoints([inTCadLyr, inModalCompLyr], INTERSECTED_LYRS)
dissolvedIntPoints = dissolveFeatures(intersectionPoints, DISSOLVED_FEATS_01)

## intersect the modal comp layer on itself to create intersection points
## where modal comp layer does not intersect the transcad layer (see AKALAKALA ST)
modalSelfIntrPoints = intersectToPoints([inModalCompLyr, inModalCompLyr], INTERSECTED_MODALS) 
dissolvedIntModalPnts = dissolveFeatures(modalSelfIntrPoints, DISSOLVED_FEATS_02)

## merge the intersections
mergeDs = "{};{}".format(dissolvedIntPoints, dissolvedIntModalPnts)
result = arcpy.management.Merge(mergeDs, MERGE_INTS, None, "NO_SOURCE_INFO")
mergedIntPoints = result.getOutput(0)
getMsgs("Merged {} and {} into {}".format(dissolvedIntPoints, dissolvedIntModalPnts, mergedIntPoints))

## buffer the output points (intersections) to create erase shapes
bufferedIntersections = doBuffer(mergedIntPoints, BUFFERED_INTERSECTIONS, "25 Feet")

## erase the input modal data so that there's distance between modal composite features 
## and transcad data
erasedModalFeatures = doErase(inModalCompLyr, bufferedIntersections, ERASE_INTERSECTIONS)

## buffer the input transcad layer to create a search shape
tCadBufOutput = doBuffer(inTCadLyr, BUFFERED_TCAD, buffDist)

# clip the erasedModalFeatures using the buffered transcad features
# This creates modal features to search
result = arcpy.analysis.Clip(erasedModalFeatures, tCadBufOutput, CADBUF_ERASE_MODAL)
modalToTCadFeatures = result.getOutput(0)
getMsgs("Clipped {} using {} to create {}".format(erasedModalFeatures, tCadBufOutput, modalToTCadFeatures))

## create a feature layer from features with length < clipLength
result = arcpy.management.MakeFeatureLayer(modalToTCadFeatures, "{}_lyr".format(CADBUF_ERASE_MODAL), "Shape_Length <= {}".format(clipLength), None)
modalToTCadFeaturesLyr = result.getOutput(0)
result = arcpy.management.GetCount(modalToTCadFeaturesLyr)
cnt = int(result.getOutput(0))
getMsgs("Feature Count in {} = {}".format(modalToTCadFeaturesLyr, cnt))

#  if there are features within this feature layer, remove them
if cnt > 0:
    arcpy.management.DeleteFeatures(modalToTCadFeaturesLyr)
    # remove them to reduce false positives
    result = arcpy.management.GetCount(modalToTCadFeaturesLyr)
    cnt01 = int(result.getOutput(0))
    getMsgs("Removed {} features from {}".format((cnt - cnt01), modalToTCadFeatures))

# search for modal features within the buffer using a spatial join
result = arcpy.analysis.SpatialJoin(modalToTCadFeatures, tCadBufOutput, SEGS_S_JOIN_TCAD, "JOIN_ONE_TO_ONE", "KEEP_COMMON", match_option=matchOption)
segmentIdsWithTcadOID = result.getOutput(0)
getMsgs("Spatial Join {} to {} using within operator to create {}".format(modalToTCadFeatures, tCadBufOutput, segmentIdsWithTcadOID))

# the result of the spatial operation contains all segmentIDs w/in 20' of a Transcad Line
# get unique segmentids + tCAD OIDs
result = arcpy.analysis.Frequency(segmentIdsWithTcadOID, FREQ_SEGID_TCADOID, "SEGMENTID;ORIG_FID", None)
freqSegsTCADOids = result.getOutput(0)
getMsgs("Created frequency table of segmentids and transcade IDs from {}".format(segmentIdsWithTcadOID))

## copy the inModalCompLyr to the output so we don't alter the input datasets
## the copy is also the output layer
result = arcpy.management.CopyFeatures(inModalCompLyr, OUT_MODAL_JOINED_LYR)
modalCopyDS = result.getOutput(0)
getMsgs("Created final output layer {} from {}".format(modalCopyDS, inModalCompLyr))

#join field back to the modal dataset copied to modalCopyDS
arcpy.management.JoinField(modalCopyDS, "SEGMENTID", freqSegsTCADOids, "SEGMENTID", "ORIG_FID")
getMsgs("Joined {} to {} on SEGMENTID".format(freqSegsTCADOids, modalCopyDS))

arcpy.management.AlterField(modalCopyDS, "ORIG_FID", renameField, renameFldAlias, "LONG", 4, "NULLABLE", "DO_NOT_CLEAR")
getMsgs("Renamed ORIG_FID to {} in {}".format(renameFldAlias, modalCopyDS))

arcpy.SetParameter(9, modalCopyDS)

if preserveDerivativeData:
    cleanUp(tCadBufOutput)
    cleanUp(erasedModalFeatures)
    cleanUp(intersectionPoints)
    cleanUp(bufferedIntersections)
    cleanUp(modalToTCadFeatures)
    cleanUp(segmentIdsWithTcadOID)
    cleanUp(freqSegsTCADOids)
    cleanUp(modalSelfIntrPoints)
    cleanUp(dissolvedIntPoints)
    cleanUp(dissolvedIntModalPnts)
    cleanUp(mergedIntPoints)

