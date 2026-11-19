Attribute VB_Name = "BuildCompressor"
'==============================================================================
' Opens every part STEP of one compressor, merges the bodies of multi-body parts
' (rotor = rim/web + boss + blades, stator-casing = ring + vanes, frames, spools, shaft)
' with Combine-Add, saves each as SLDPRT, then builds a SLDASM with all parts fixed at
' the origin (all parts are modelled in assembly coordinates).
' Written without access to SolidWorks - UNTESTED. If a step fails, use the manual route
' in README.txt (open the assembly STEP directly).
' Before running: Tools > Options > System Options > Import > STEP: units mm.
'==============================================================================
Option Explicit
Dim swApp As SldWorks.SldWorks
Sub main()
    Set swApp = Application.SldWorks
    Dim root As String, f As String, outDir As String
    root = InputBox("Folder of one compressor (the one that contains parts_STEP):", "Build compressor", "C:\Compressor_5stage")
    If root = "" Then Exit Sub
    If Right(root, 1) = "\" Then root = Left(root, Len(root) - 1)
    outDir = root & "\SolidWorks\": If Dir(outDir, vbDirectory) = "" Then MkDir outDir
    Dim names As New Collection
    f = Dir(root & "\parts_STEP\*.step")
    Do While f <> ""
        names.Add Replace(f, ".step", "")
        f = Dir
    Loop
    Dim i As Long
    For i = 1 To names.Count
        If Not ConvertPart(root & "\parts_STEP\" & names(i) & ".step", outDir & names(i) & ".SLDPRT") Then
            MsgBox "Could not convert " & names(i), vbExclamation
        End If
    Next
    Dim tmpl As String, m As SldWorks.ModelDoc2, a As SldWorks.AssemblyDoc, c As SldWorks.Component2, e As Long, w As Long
    tmpl = swApp.GetUserPreferenceStringValue(swUserPreferenceStringValue_e.swDefaultTemplateAssembly)
    Set m = swApp.NewDocument(tmpl, 0, 0, 0): Set a = m
    For i = 1 To names.Count
        Set c = a.AddComponent5(outDir & names(i) & ".SLDPRT", 0, "", False, "", 0#, 0#, 0#)
        If Not c Is Nothing Then
            c.Select4 False, Nothing, False: a.FixComponent: m.ClearSelection2 True
        End If
    Next
    m.ViewZoomtofit2
    m.Extension.SaveAs outDir & "Compressor_Assembly.SLDASM", 0, 1, Nothing, e, w
    MsgBox names.Count & " parts converted. Assembly saved in " & outDir
End Sub
Private Function ConvertPart(src As String, dst As String) As Boolean
    Dim m As SldWorks.ModelDoc2, p As SldWorks.PartDoc, b As Variant, e As Long, w As Long, n As Long, i As Long
    Dim imp As Object
    Set imp = swApp.GetImportFileData(src)
    Set m = swApp.LoadFile4(src, "r", imp, e)
    If m Is Nothing Then Exit Function
    Set p = m: b = p.GetBodies2(0, False)          ' 0 = swSolidBody
    If Not IsEmpty(b) Then
        n = UBound(b) - LBound(b) + 1
        If n > 1 Then
            Dim tools() As Object: ReDim tools(n - 1)
            For i = 0 To n - 1: Set tools(i) = b(LBound(b) + i): Next
            m.ClearSelection2 True
            m.FeatureManager.InsertCombineFeature 15903, Nothing, tools   ' 15903 = swBodyOperationType_e.SWBODYADD
        End If
    End If
    ConvertPart = m.Extension.SaveAs(dst, 0, 1, Nothing, e, w)
    swApp.CloseDoc m.GetTitle
End Function
