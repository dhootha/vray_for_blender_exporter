#
# V-Ray For Blender
#
# http://chaosgroup.com
#
# Author: Andrei Izrantcev
# E-Mail: andrei.izrantcev@chaosgroup.com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# All Rights Reserved. V-Ray(R) is a registered trademark of Chaos Software.
#

import math
import os
import tempfile

import bpy

from . import LibUtils
from . import PathUtils


ObjectPrefix = {
    'LAMP'   : 'LA',
    'CAMERA' : 'CA',
}

NonGeometryTypes = {'LAMP','CAMERA','SPEAKER','ARMATURE','LATTICE','EMPTY'}

NC_WORLD    = 0
NC_MATERIAL = 1
NC_LAMP     = 3


def GeometryObjectIt(scene):
    for ob in scene.objects:
        if ob.type not in NonGeometryTypes:
            yield ob


def SceneLampIt(scene, obType=None):
    for ob in scene.objects:
        if ob.type == 'LAMP':
            yield ob


def ObjectMaterialsIt(objects):
    for ob in objects:
        if not len(ob.material_slots):
            continue
        for ms in ob.material_slots:
            if not ms.material:
                continue
            yield ms.material


def ObjectTexturesIt(objects):
    for ob in objects:
        if not len(ob.material_slots):
            continue
        for ms in ob.material_slots:
            if not ms.material:
                continue
            for ts in ms.material.texture_slots:
                if ts and ts.texture:
                    yield ts.texture


def IsTexturePreview(scene):
    texPreviewOb = scene.objects.get('texture', None)
    if texPreviewOb and texPreviewOb.is_visible(scene):
        return texPreviewOb
    return None


def GetPreviewTexture(ob):
    if not len(ob.material_slots):
        return None
    if not ob.material_slots[0].material:
        return None
    ma = ob.material_slots[0].material
    if not len(ma.texture_slots):
        return None
    slot = ma.texture_slots[0]
    if not slot.texture:
        return None
    return slot.texture


def IsAnimated(o):
    if o.animation_data and o.animation_data.action:
        return True
    elif hasattr(o, 'parent') and o.parent:
        return IsAnimated(o.parent)
    return False


def IsDataAnimated(o):
    if not o.data:
        return False
    if o.data.animation_data and o.data.animation_data.action:
        return True
    return False


def GetObjectList(object_names_string=None, group_names_string=None):
    object_list = []

    if object_names_string:
        ob_names = object_names_string.split(';')
        for ob_name in ob_names:
            if ob_name in bpy.data.objects:
                object_list.append(bpy.data.objects[ob_name])

    if group_names_string:
        gr_names = group_names_string.split(';')
        for gr_name in gr_names:
            if gr_name in bpy.data.groups:
                object_list.extend(bpy.data.groups[gr_name].objects)

    dupliGroup = []
    for ob in object_list:
        if ob.dupli_type == 'GROUP' and ob.dupli_group:
            dupliGroup.extend(ob.dupli_group.objects)
    object_list.extend(dupliGroup)

    return object_list


def GetCameraHideLists(camera):
    VRayCamera = camera.data.vray

    visibility = {
        'all'     : set(),
        'camera'  : set(),
        'gi'      : set(),
        'reflect' : set(),
        'refract' : set(),
        'shadows' : set(),
    }

    if VRayCamera.hide_from_view:
        for hide_type in visibility:
            if getattr(VRayCamera, 'hf_%s' % hide_type):
                if getattr(VRayCamera, 'hf_%s_auto' % hide_type):
                    obList = GetObjectList(group_names_string='hf_%s' % camera.name)
                else:
                    obList = GetObjectList(getattr(VRayCamera, 'hf_%s_objects' % hide_type),
                                           getattr(VRayCamera, 'hf_%s_groups' % hide_type))
                for o in obList:
                    visibility[hide_type].add(o.as_pointer())

    return visibility


def GetEffectsExcludeList(scene):
    # TODO: Rewrite to nodes!
    #
    VRayScene = scene.vray
    exclude_list = []
    VRayEffects  = VRayScene.VRayEffects
    if VRayEffects.use:
        for effect in VRayEffects.effects:
            if effect.use:
                if effect.type == 'FOG':
                    EnvironmentFog = effect.EnvironmentFog
                    fog_objects = GetObjectList(EnvironmentFog.objects, EnvironmentFog.groups)
                    for ob in fog_objects:
                        if ob not in exclude_list:
                            exclude_list.append(ob.as_pointer())
    return exclude_list


def FilterObjectListByType(objectList, objectType):
    return filter(lambda x: x.type == objectType, objectList)


def GetObjectName(ob, prefix=None):
    if prefix is None:
        prefix = ObjectPrefix.get(ob.type, 'OB')
    name = prefix + ob.name
    if ob.library:
        name = 'LI' + PathUtils.GetFilename(ob.library.filepath) + name
    return LibUtils.CleanString(name)


def GetGroupObjects(groupName):
    obList = []
    if groupName in bpy.data.groups:
        obList.extend(bpy.data.groups[groupName].objects)
    return obList


def GetGroupObjectsNames(groupName):
    obList = [GetObjectName(ob) for ob in GetGroupObjects(groupName)]
    return obList


def GetSmokeModifier(ob):
    if len(ob.modifiers):
        for md in ob.modifiers:
            if md.type == 'SMOKE' and md.smoke_type == 'DOMAIN':
                return md
    return None


def GetSceneObject(scene, objectName):
    if objectName not in scene.objects:
        return None
    return scene.objects[objectName]


def GetDistanceObOb(ob1, ob2):
    t1 = ob1.matrix_world.translation
    t2 = ob2.matrix_world.translation
    d = t1 - t2
    return d.length


def GetCameraDofDistance(ca):
    dofDistance = ca.data.dof_distance

    dofObject = ca.data.dof_object
    if dofObject:
        dofDistance = GetDistanceObOb(ca, dofObject)

    return dofDistance


def GetCameraFOV(scene, camera):
    VRayCamera = camera.data.vray

    fov = VRayCamera.fov if VRayCamera.override_fov else camera.data.angle

    orthoWidth = camera.data.ortho_scale
    aspect     = scene.render.resolution_x / scene.render.resolution_y

    if aspect < 1.0:
        fov = 2 * math.atan(math.tan(fov/2.0) * aspect)
        orthoWidth *= aspect

    return fov, orthoWidth


def ObjectOnVisibleLayers(scene, ob):
    VRayScene = scene.vray
    VRayExporter = VRayScene.Exporter

    if VRayExporter.activeLayers == 'ALL':
        return True

    activeLayers = scene.layers
    if VRayExporter.activeLayers == 'CUSTOM':
        activeLayers = VRayExporter.customRenderLayers

    for l in range(20):
        if ob.layers[l] and activeLayers[l]:
            return True

    return False


def ObjectVisible(bus, ob):
    scene = bus['scene']

    VRayScene = scene.vray
    VRayExporter    = VRayScene.Exporter
    SettingsOptions = VRayScene.SettingsOptions

    if not ObjectOnVisibleLayers(scene,ob):
        if ob.type == 'LAMP':
            if not SettingsOptions.light_doHiddenLights:
                return False
        if not SettingsOptions.geom_doHidden:
            return False

    if ob.hide_render:
        if ob.type == 'LAMP':
            if not SettingsOptions.light_doHiddenLights:
                return False
        if not SettingsOptions.geom_doHidden:
            return False

    return True


def IsPathRelative(path):
    return path.startswith("//")


def RelativePathValid(path):
    if not IsPathRelative(path):
        return True
    if bpy.data.filepath:
        return True
    return False


def GetFullFilepath(filepath, holder=None):
    fullFilepath = filepath

    if not IsPathRelative(filepath):
        fullFilepath = filepath

    elif not (holder and holder.library):
        if RelativePathValid(filepath):
            fullFilepath = bpy.path.abspath(filepath)
        else:
            fullFilepath = os.path.join(tempfile.gettempdir(), filepath[2:])

    else:
        # Path is from linked library and is relative
        # Remove "//"
        # filepath = filepath[2:]

        # Use library dirpath as relative root
        # libraryDirpath = os.path.dirname(bpy.path.abspath(holder.library.filepath))

        # fullFilepath = os.path.normpath(os.path.join(libraryDirpath, filepath))
        fullFilepath = bpy.path.abspath(filepath, library=holder.library)

    fullFilepath = os.path.normpath(fullFilepath)

    return fullFilepath


def AddEvent(event, func):
    if func not in event:
        event.append(func)


def DelEvent(event, func):
    if func in event:
        event.remove(func)


def SelectObject(ob):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.objects.active = ob
    ob.select = True


def IsPreviewWorld(scene):
    return scene.layers[7]


def GetSceneAndCamera(bus):
    scene  = bus['scene']
    camera = bus['camera']
    engine = bus['engine']

    # Use camera from current scene for world preview
    if engine and engine.is_preview:
        if IsPreviewWorld(scene):
            scene = bpy.context.scene
            if scene.camera:
                camera = scene.camera

    return scene, camera


def generateVfbTheme(filepath):
    import mathutils

    def rgbToHex(color):
        return '#%X%X%X' % (int(color[0] * 255), int(color[1] * 255), int(color[2] * 255))

    currentTheme = bpy.context.user_preferences.themes[0]

    themeUI   = currentTheme.user_interface
    themeProp = currentTheme.properties

    back   = rgbToHex(themeProp.space.back)
    text   = rgbToHex(themeProp.space.text)
    header = rgbToHex(themeProp.space.header)

    buttonColorTuple = themeUI.wcol_tool.inner
    buttonColor = mathutils.Color((buttonColorTuple[0], buttonColorTuple[1], buttonColorTuple[2]))

    button = rgbToHex(buttonColor)

    buttonColor.v *= 1.35
    buttonHover = rgbToHex(buttonColor)

    shadow = rgbToHex(themeUI.wcol_tool.outline)

    pressed = rgbToHex(themeUI.wcol_radio.inner_sel)
    hover   = rgbToHex(themeUI.wcol_tool.inner_sel)

    rollout = rgbToHex(themeUI.wcol_box.inner)

    import xml.etree.ElementTree
    from xml.etree.ElementTree import Element, SubElement, tostring

    elVfb = Element("VFB")
    elTheme = SubElement(elVfb, "Theme")

    SubElement(elTheme, "style").text = "Standalone"

    # This is the color under the rendered image, just keep it dark.
    SubElement(elTheme, "appWorkspace").text   = "#222222"

    SubElement(elTheme, 'window').text         = back
    SubElement(elTheme, 'windowText').text     = text
    SubElement(elTheme, 'btnFace').text        = button
    SubElement(elTheme, 'btnFacePressed').text = pressed
    SubElement(elTheme, 'btnFaceHover').text   = buttonHover
    SubElement(elTheme, 'hover').text          = hover
    SubElement(elTheme, 'rollout').text        = rollout
    SubElement(elTheme, 'hiLight').text        = shadow
    SubElement(elTheme, 'darkShadow').text     = shadow

    tree = xml.etree.ElementTree.ElementTree(elVfb) 

    with open(filepath, 'wb') as f:
        tree.write(f, encoding='utf-8')
