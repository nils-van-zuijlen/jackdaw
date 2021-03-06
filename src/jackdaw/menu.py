import os
import sys
import re
import glob
import functools

from PySide.QtCore import *
from PySide.QtGui import *

import icon
from model import Selection
from undo import UndoManager

import sampler
import audio
import transport
import track
import midi
from unit import Unit, GroupUnit

# this class holds the stack of views and models a context click 
#  might refer to
class ContextMenu(QMenu):
  # keep a map from view classes to the context menus that should be 
  #  shown for them
  _context_map = dict()
  def __init__(self, item, event, parent=None, view=None):
    QMenu.__init__(self, parent)
    # navigate up the view chain and add to the context
    menus = list()
    while (item is not None):
      class_name = item.__class__.__name__
      if (class_name in self._context_map):
        self.add_menu(item, event, class_name, menus)
      for key in self._context_map.iterkeys():
        if (('*' in key) and (re.match(key, class_name))):
          self.add_menu(item, event, key, menus)
      item = item.parentItem()
    # build menus after model properties have been set so they're accessible
    #  from all menus via this class
    for (menu_class, kwargs) in menus:
      menu = menu_class(**kwargs)
      self.addMenu(menu)
  # add a menu for the given key in the context map
  def add_menu(self, item, event, key, menus):
    (menu_class, attributes) = self._context_map[key]
    kwargs = dict()
    kwargs['parent'] = self
    kwargs['event'] = event
    kwargs['view'] = item
    for attribute in attributes:
      model = getattr(item, attribute)
      # pass model properties as keyword arguments to the menu
      kwargs[attribute] = model
      # add all model properties to the current class so they can be used
      #  by menus to walk up the hierarchy
      setattr(self, attribute, model)
    if (menu_class is not None):
      menus.append((menu_class, kwargs))
  # register a menu class for a certain model/view type
  @classmethod
  def register_context(cls, view_class_name, menu_class, model_attributes):
    cls._context_map[view_class_name] = (menu_class, model_attributes)
  # return whether a class is registered to receive context menu events
  @classmethod
  def has_menu_for_view(cls, item):
    class_name = item.__class__.__name__
    for key in cls._context_map.iterkeys():
      if (re.match(key, class_name)):
        (menu_class, model_attributes) = cls._context_map[key]
        if (menu_class is not None): return(True)
    return(False)
ContextMenu.register_context('TrackListView', None, ('tracks',))

class WorkspaceMenu(QMenu):
  def __init__(self, document, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Add Unit')
    self.setIcon(icon.get('workspace'))
    self.document = document
    self.units = document.units
    self.scene_pos = event.scenePos()
    self.add_action('midi', 'MIDI Inputs', 
                    'Add a MIDI instrument input unit', self.on_add_midi_input)
    self.add_action('transport', 'Transport', 
                    'Add a transport control unit', self.on_add_transport)
    self.add_action('tracks', 'Sequencer', 
                    'Add a unit for MIDI recording and playback', 
                    self.on_add_sequencer)
    self.add_action('instrument', 'Sampler Instrument...', 
                    'Add a sampler unit', self.on_add_sampler)
    self.add_action('speaker', 'Audio Output', 
                    'Add a system audio output unit', self.on_add_audio_output)
    self.add_action('data', 'MIDI Monitor', 
                    'Add a visual MIDI message monitor', self.on_add_midi_monitor)
  def add_action(self, icon_name, name, description, callback):
    action = QAction(icon.get(icon_name), name, self)
    action.setStatusTip(description)
    action.triggered.connect(callback)
    self.addAction(action)
  # add a generic unit
  def add_unit(self, new_unit):
    UndoManager.begin_action(self.units)
    self.units.append(new_unit)
    UndoManager.end_action()
  # add a MIDI input
  def on_add_midi_input(self, *args):
    self.add_unit(midi.DeviceListUnit(
        name='MIDI Inputs',
        devices=self.document.devices,
        require_input=False,
        require_output=True,
        x=self.scene_pos.x(),
        y=self.scene_pos.y()))
  # add a sampler
  def on_add_sampler(self, *args):
    instrument = sampler.Instrument.new_from_browse()
    if (instrument is None): return
    instruments = sampler.InstrumentList([ instrument ])
    self.add_unit(sampler.InstrumentListUnit(
        name='Sampler',
        instruments=instruments,
        x=self.scene_pos.x(),
        y=self.scene_pos.y()))
  # add an audio output
  def on_add_audio_output(self, *args):
    self.add_unit(audio.SystemPlaybackUnit(
        name='Audio Out',
        x=self.scene_pos.x(),
        y=self.scene_pos.y()))
  # add a transport controller
  def on_add_transport(self, *args):
    self.add_unit(transport.TransportUnit(
        transport=self.document.transport,
        name='Transport',
        x=self.scene_pos.x(),
        y=self.scene_pos.y()))
  # add a sequencer unit
  def on_add_sequencer(self, *args):
    empty_track = track.Track(transport=self.document.transport)
    tracks = track.TrackList(
      tracks=(empty_track,),
      transport=self.document.transport)
    self.add_unit(track.SequencerUnit(
        tracks=tracks,
        view_scale=self.document.view_scale,
        transport=self.document.transport,
        name='Sequencer',
        x=self.scene_pos.x(),
        y=self.scene_pos.y()))
  # add a midi monitor
  def on_add_midi_monitor(self, *args):
    self.add_unit(midi.MidiMonitorUnit(
        name='Monitor',
        x=self.scene_pos.x(),
        y=self.scene_pos.y()))
ContextMenu.register_context('WorkspaceView', WorkspaceMenu, ('document',))

# make a context menu for an instrument
class InstrumentMenu(QMenu):
  def __init__(self, instrument, event, parent=None, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Instrument')
    self.setIcon(icon.get('instrument'))
    self.instrument = instrument
    self.document = parent.document
    self.instruments = parent.instruments
    if (len(self.instrument.path) > 0):
      (name, ext) = os.path.splitext(os.path.basename(self.instrument.path))
      search_dir = os.path.dirname(self.instrument.path)
      for path in glob.glob(os.path.join(search_dir, '*'+ext)):
        (name, ext) = os.path.splitext(os.path.basename(path))
        action = QAction(name, self)
        is_current = (path == self.instrument.path)
        action.setEnabled(not is_current)
        action.setCheckable(is_current)
        action.setChecked(is_current)
        action.triggered.connect(functools.partial(self.on_change_path, path))
        self.addAction(action)
      self.addSeparator()
    action = QAction(icon.get('instrument'), 'Browse...', self)
    action.triggered.connect(self.on_browse)
    self.addAction(action)
    if (self.instruments):
      action = QAction(icon.get('delete'), 'Remove', self)
      action.triggered.connect(self.on_remove)
      self.addAction(action)
  def on_change_path(self, path):
    UndoManager.begin_action(self.instrument)
    self.instrument.path = path
    UndoManager.end_action()
  def on_browse(self):
    UndoManager.begin_action(self.instrument)
    self.instrument.browse()
    UndoManager.end_action()
  def on_remove(self):
    UndoManager.begin_action((self.instruments, self.document))
    if (self.document is not None):
      self.document.patch_bay.remove_connections_for_unit(self.instrument)
    self.instruments.remove(self.instrument)
    UndoManager.end_action()
ContextMenu.register_context('InstrumentView', InstrumentMenu, ('instrument',))
ContextMenu.register_context('InstrumentListView', None, ('instruments',))

class TransportUnitMenu(QMenu):
  def __init__(self, unit, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Transport')
    self.setIcon(icon.get('transport'))
    self.transport = unit.transport
    protocols = self.transport.protocols
    menu = QMenu()
    menu.setIcon(icon.get('data'))
    menu.setTitle('MIDI Protocol')
    for protocol in protocols.iterkeys():
      (name, cls) = protocols[protocol]
      action = QAction(name, menu)
      if (protocol == self.transport.protocol):
        action.setIcon(icon.get('check'))
      action.triggered.connect(functools.partial(self.on_protocol, protocol))
      menu.addAction(action)
    self.addMenu(menu)
  def on_protocol(self, protocol):
    self.transport.protocol = protocol
ContextMenu.register_context('TransportUnitView', TransportUnitMenu, ('unit',))

class TrackMenu(QMenu):
  def __init__(self, track, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Track')
    self.setIcon(icon.get('track'))
    self.track = track
    try:
      self.tracks = parent.tracks
    except AttributeError:
      self.tracks = None
    try:
      self.patch_bay = parent.document.patch_bay
    except AttributeError:
      self.patch_bay = None
    delete_action = QAction(icon.get('delete'), 'Delete', self)
    delete_action.setStatusTip('Delete this track')
    delete_action.triggered.connect(self.on_delete)
    self.addAction(delete_action)
  # delete the block
  def on_delete(self, *args):
    UndoManager.begin_action((self.tracks, self.patch_bay))
    self.tracks.remove(self.track)
    UndoManager.end_action()
ContextMenu.register_context('TrackView', TrackMenu, ('track',))

class BlockMenu(QMenu):
  def __init__(self, block, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Block')
    self.setIcon(icon.get('block'))
    self.block = block
    try:
      self.tracks = parent.tracks
    except AttributeError:
      self.tracks = None
    split_action = QAction(icon.get('split'), 'Split', self)
    split_action.setStatusTip('Split the block into multiple blocks')
    split_action.triggered.connect(self.on_split)
    self.addAction(split_action)
    join_action = QAction(icon.get('join'), 'Join', self)
    join_action.setStatusTip('Join selected blocks into one')
    join_action.triggered.connect(self.on_join)
    self.addAction(join_action)
    self.addMenu(HueMenu(self.block.events, self))
    delete_action = QAction(icon.get('delete'), 'Delete', self)
    delete_action.setStatusTip('Delete this block')
    delete_action.triggered.connect(self.on_delete)
    self.addAction(delete_action)
    # disable actions that can't be performed
    # get all the selected blocks
    selected = self.get_selected_blocks()
    # if the block is the only one selected, it can be split
    split_action.setEnabled((len(selected) == 0) or 
      ((len(selected) == 1) and (self.block in selected)))
    # if more than one block is selected, they can be joined
    join_action.setEnabled(
      (len(selected) == 0) or (self.block in selected))
  # get all blocks in the selection
  def get_selected_blocks(self):
    blocks = set()
    for item in Selection.models:
      if (hasattr(item, 'events')):
        blocks.add(item)
    return(blocks)
  # get selected events within the current block
  def get_selected_notes(self):
    block_events = set(self.block.events)
    selected_events = set()
    for item in Selection.models:
      if ((item in block_events) and (hasattr(item, 'pitch'))):
        selected_events.add(item)
    return(selected_events)
  # join multiple blocks
  def on_join(self, *args):
    blocks = self.get_selected_blocks()
    blocks.add(self.block)
    UndoManager.begin_action((blocks, self.tracks))
    if (len(blocks) > 1):
      self.block.join(blocks, tracks=self.tracks)
    else:
      self.block.join_repeats()
    UndoManager.end_action()
  # split a block at selected note boundaries
  def on_split(self, *args):
    current_track = None
    for track in self.tracks:
      if (self.block in track):
        current_track = track
        break
    # if the block has multiple repeats, split the repeats
    if (self.block.events.duration < self.block.duration):
      UndoManager.begin_action(track)
      self.block.split_repeats(track=current_track)
      UndoManager.end_action()
    else:
      times = [ ]
      # get selected events in the block
      selected_events = self.get_selected_notes()
      # if events are selected in the block, find boundaries 
      #  between selected and deselected events
      if (len(selected_events) > 0):
        # sort all block events by time
        events = list(self.block.events)
        events.sort(key=lambda e: e.time)
        # find boundaries
        was_selected = (events[0] in selected_events)
        for event in events:
          # count notes only
          if (not hasattr(event, 'pitch')): continue
          is_selected = (event in selected_events)
          if (is_selected != was_selected):
            times.append(event.time)
            was_selected = is_selected
      # if there are times to split on, we can split
      if (len(times) > 0):
        UndoManager.begin_action((self.block, current_track))
        self.block.split(times, track=current_track)
        UndoManager.end_action()
  # delete the block
  def on_delete(self, *args):
    current_track = None
    for track in self.tracks:
      if (self.block in track):
        current_track = track
        break
    if (current_track is None): return
    UndoManager.begin_action(current_track)
    current_track.remove(self.block)
    UndoManager.end_action()
ContextMenu.register_context('BlockView', BlockMenu, ('block',))

# make a context menu for a controller view
class ControllerMenu(QMenu):
  def __init__(self, events, number, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Controller %d' % number)
    self.setIcon(icon.get('controller'))
    self.events = events
    self.number = number
    change_action = QAction('Change number', self)
    change_action.setStatusTip('Change the number of this controller')
    change_action.triggered.connect(self.on_change)
    self.addAction(change_action)
    delete_action = QAction(icon.get('delete'), 'Delete', self)
    delete_action.setStatusTip(
      'Delete all changes on controller %d' % self.number)
    delete_action.triggered.connect(self.on_delete)
    self.addAction(delete_action)
  def on_change(self):
    dialog = QInputDialog()
    dialog.setLabelText('Change controller number %d to:' % self.number)
    dialog.setInputMode(QInputDialog.IntInput)
    dialog.setIntRange(0, 119)
    dialog.setIntValue(self.number)
    if (dialog.exec_() != 0):
      new_number = dialog.intValue()
      if (new_number != self.number):
        self.events.remap_ccsets(self.number, new_number)
  def on_delete(self):
    self.events.begin_change_block()
    for event in set(self.events):
      try:
        number = event.number
        value = event.value
      except AttributeError: continue
      if (number == self.number):
        self.events.remove(event)
    self.events.end_change_block()
ContextMenu.register_context('ControllerView', ControllerMenu, ('events', 'number'))

# make a context menu for a unit
class UnitMenu(QMenu):
  def __init__(self, unit, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Unit')
    self.setIcon(icon.get('unit'))
    self.unit = unit
    self.view = view
    selected_units = self.selected_units()
    if ((self.unit in selected_units) and 
        (len(selected_units) > 1)):
      action = QAction('Group Selected Units', self)
      action.setStatusTip('Add the selected units to a group')
      action.triggered.connect(self.on_group)
      self.addAction(action)
    self.addMenu(HueMenu(self.unit, self))
    delete_action = QAction(icon.get('delete'), 'Delete', self)
    delete_action.setStatusTip('Delete %s' % self.unit.name)
    delete_action.triggered.connect(self.on_delete)
    self.addAction(delete_action)
  # get all selected units
  def selected_units(self):
    units = set()
    for unit in Selection.models:
      if (isinstance(unit, Unit)):
        units.add(unit)
    return(units)
  def on_delete(self):
    self.view.on_delete()
  def on_group(self):
    workspace_view = self.view.parentItemWithAttribute('document')
    if (workspace_view is None): return
    units = workspace_view.document.units
    selected_units = self.selected_units()
    UndoManager.begin_action(units)
    units.append(GroupUnit(units=selected_units, name='Group'))
    UndoManager.end_action()
ContextMenu.register_context('.*UnitView', UnitMenu, ('unit',))

# make a context menu for midi monitor unit
class MidiMonitorMenu(QMenu):
  def __init__(self, unit, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('MIDI Monitor')
    self.setIcon(icon.get('data'))
    self.unit = unit
    self.style_menu = QMenu(self)
    self.style_menu.setTitle('Style')
    styles = (('hex', 'Hexadecimal'), 
              ('decimal', 'Decimal'),
              ('binary', 'Binary'))
    for (style, label) in styles:
      action = QAction(label, self.style_menu)
      action.setStatusTip(
        'Set the display style to %s' % label.lower())
      action.triggered.connect(functools.partial(self.on_set_style, style))
      if (style == self.unit.style):
        action.setIcon(icon.get('check'))
      self.style_menu.addAction(action)
    self.addMenu(self.style_menu)
    action = QAction('Show Time', self)
    action.setStatusTip('Show the times of MIDI events')
    action.triggered.connect(self.on_toggle_show_time)
    if (self.unit.show_time):
      action.setIcon(icon.get('check'))
    self.addAction(action)
  def on_set_style(self, style):
    self.unit.style = style
  def on_toggle_show_time(self):
    self.unit.show_time = not self.unit.show_time
ContextMenu.register_context('MidiMonitorUnitView', MidiMonitorMenu, ('unit',))

# make a context menu for a connection
class ConnectionMenu(QMenu):
  def __init__(self, connection, event, parent, view=None):
    QMenu.__init__(self, parent)
    self.setTitle('Connection')
    self.setIcon(icon.get('connection'))
    self.connection = connection
    self.view = view
    self.addMenu(HueMenu(self.connection, self))
    delete_action = QAction(icon.get('delete'), 'Disconnect', self)
    delete_action.setStatusTip('Remove this connection')
    delete_action.triggered.connect(self.view.on_delete)
    self.addAction(delete_action)
ContextMenu.register_context('ConnectionView', ConnectionMenu, ('connection',))

# make a menu to select colors for an element
class HueMenu(QMenu):
  def __init__(self, target, parent):
    QMenu.__init__(self, parent)
    self._target = target
    self.setTitle('Color')
    self.setIcon(icon.get('colors'))
    hues = (
      ('None', None),
      ('Red', 0),
      ('Orange', 30),
      ('Yellow', 60),
      ('Green', 120),
      ('Cyan', 180),
      ('Blue', 220),
      ('Purple', 270),
      ('Magenta', 330)
    )
    for (name, hue) in hues:
      action = QAction(name, self)
      if (hue is not None):
        hue = (hue / 360.0)
        color = QColor()
        color.setHsvF(hue, 1.0, 1.0)
        action.setIcon(icon.get('color', color))
      else:
        action.setIcon(icon.get('color_none'))
      action.triggered.connect(functools.partial(self.on_hue, hue))
      self.addAction(action)
  def on_hue(self, hue):
    self._target.hue = hue