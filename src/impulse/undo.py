from PySide.QtCore import *

import types
import collections
import observable
from model import Selection

# manage a stack of states to implement undo/redo functionality
#  on a collection of objects implementing the Observable mixin
class UndoStack(object):
  def __init__(self):
    self.actions = [ ]
    self.position = 0
    self._begin_state = None
  # store the state of the given objects before changes are made
  def begin_action(self, things):
    self._begin_state = self.save_state(things)
  # add items to the beginning state
  def add_to_action(self, things):
    new_state = self.save_state(things)
    for (key, value) in new_state.iteritems():
      if (key not in self._begin_state):
        self._begin_state[key] = value
  # store the state of the given objects after changes are made
  def end_action(self, things):
    # if no action was in the works, we can skip this
    if (self._begin_state is None): return
    # see what changed in the course of the action
    begin_state = self._begin_state
    end_state = self.save_state(things)
    keys = end_state.keys()
    for key in keys:
      if ((key in begin_state) and 
          (begin_state[key] == end_state[key])):
        del begin_state[key]
        del end_state[key]
    # clear the stored beginning state
    self._begin_state = None
    # if no changes were made, don't record an action
    if ((len(begin_state) == 0) and (len(end_state) == 0)): return
    # remove all actions past the current position
    self.actions = self.actions[0:self.position]
    # add a reversible action to the stack
    self.actions.append((begin_state, end_state))
    self.position += 1
  
  # return whether it's possible to undo/redo
  @property
  def can_undo(self):
    return((self.position is not None) and 
           (self.position > 0))
  @property
  def can_redo(self):
    return((self.position is not None) and 
           (self.position < len(self.actions)))
           
  # undo the last action
  def undo(self):
    if (not self.can_undo): return
    self.position -= 1
    self.restore_state(self.actions[self.position][0])
    
  # redo the last undone action
  def redo(self):
    if (not self.can_redo): return
    self.restore_state(self.actions[self.position][1])
    self.position += 1
    
  # walk all attributes and members of the given items and store them
  #  to a single dictionary
  def save_state(self, thing, state=None):
    if (state is None):
      state = collections.OrderedDict()
    # don't store the state of tuples, since they're immutable and can't
    #  be restored
    if (type(thing) is types.TupleType):
      for item in thing:
        self.save_state(item, state)
      return(state)
    # determine whether we can store the thing's state in the dict
    hashable = hasattr(thing, '__hash__')
    # if the item is a sequence, save state of all items in it
    try:
      for item in thing:
        self.save_state(item, state)
      # if the sequence can itself be hashed, store its items as a plain list
      if (hashable):
        state[(thing, '_list')] = tuple(thing)
    except TypeError: pass
    if (not hashable): return(state)
    # try to get a serialized dictionary for the thing
    try:
      d = thing.serialize()
    except AttributeError:
      try:
        d = thing.__dict__
      except AttributeError:
        return(state)
    # store the thing's attributes if it can be serialized
    for (key, value) in d.iteritems():
      # skip private stuff
      if (key[0] == '_'): continue
      # skip any methods
      if (callable(value)): continue
      # copy lists and dictionaries so we're not storing a reference
      #  to a mutable value
      if (type(value) is types.DictType):
        value = dict(value)
      elif (type(value) is types.ListType):
        value = tuple(value)
      state[(thing, key)] = value
    # store model references
    try:
      refs = thing.model_refs
    except AttributeError: pass
    else:
      self.save_state(refs, state)
    return(state)
  # restore state from a dictionary generated by calling save_state
  def restore_state(self, state):
    for (ref, value) in state.iteritems():
      (thing, key) = ref
      if (key == '_list'):
        thing[0:] = value
      else:
        try:
          setattr(thing, key, value)
        except AttributeError: pass

# make a singleton for handling an undo/redo stack
class UndoManagerSingleton(observable.Object):
  def __init__(self):
    observable.Object.__init__(self)
    self.reset()
  # reset the state of the manager
  def reset(self):
    self._undo_stack = UndoStack()
    self._action_things = None
    self._end_action_timer = QTimer()
    self._end_action_timer.setSingleShot(True)
    self._end_action_timer.timeout.connect(self.end_action)
    self._group = None
  # expose properties of the undo stack, adding selection restoring
  #  and event grouping
  @property
  def can_undo(self):
    return(self._undo_stack.can_undo)
  @property
  def can_redo(self):
    return(self._undo_stack.can_redo)
  def undo(self, *args):
    self._undo_stack.undo()
    self.on_change()
  def redo(self, *args):
    self._undo_stack.redo()
    self.on_change()
  def begin_action(self, things=(), end_timeout=None, group=None):
    # allow some action groups to group other actions
    if (self._group is not None):
      if (things is not None):
        if (type(things) is not types.TupleType):
          things = (things,)
        for thing in things:
          if (self._action_things is None):
            self._action_things = ()
          if (thing not in self._action_things):
            self._action_things = self._action_things + (thing,)
            self._undo_stack.add_to_action(thing)
      return
    self._group = group
    # handle timeouts
    first_one = True
    if (end_timeout is not None):
      first_one = False
      if (self._end_action_timer.isActive()):
        self._end_action_timer.stop()
      else:
        first_one = True
      self._end_action_timer.start(end_timeout)
    elif (self._end_action_timer.isActive()):
      self._end_action_timer.stop()
      self.end_action()
    if (first_one):
      self._action_things = (things, Selection, Selection.models)
      self._undo_stack.begin_action(self._action_things)
      self.on_change()
  def end_action(self, group=None):
    # end the group if we get the identifier for the outermost group
    if (self._group is not None):
      if (self._group != group): return
      self._group = None
    self._undo_stack.end_action(self._action_things)
    self._action_things = None
    self.on_change()
    self._end_action_timer.stop() 
    return(False)
# make a singleton instance
UndoManager = UndoManagerSingleton()