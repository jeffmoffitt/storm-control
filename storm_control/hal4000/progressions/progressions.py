#!/usr/bin/env python
"""
The progression control dialog box.

This dialog allows the user to configure an automatic starting 
power and power increment to use while taking STORM movies. 
This increases productivity & overall quality of life as the 
user can focus on surfing the internet while acquiring STORM 
movies without getting distracted by constantly having to adjust 
the laser powers.

Hazen 02/14
"""

import os
import sys
from PyQt5 import QtCore, QtWidgets

import storm_control.sc_library.parameters as params

import storm_control.hal4000.halLib.halDialog as halDialog
import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.halModule as halModule

import storm_control.hal4000.qtdesigner.progression_ui as progressionUi


class Channels(object):

    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.height = 40
        self.powers = []

    def handleNewFrame(self, frame_number):
        pass

    def startFilm(self):
        pass

    def stopFilm(self):
        pass


class MathChannels(Channels):
    """
    Channels class for mathematical progressions (linear, exponential).
    """
    def __init__(self, configuration = None, channels = None, x_positions = None, parent = None, **kwds):
        """
        Called to layout the GUI for math channels. These 
        channels match the channels of the illumination.
        """
        super().__init__(**kwds)

        y = 40
        dy = 26
        self.channels = []
        self.which_checked = []
        for channel in channels:
            self.powers.append(0.0)
            self.which_checked.append(False)
            channel_frame = QtWidgets.QFrame(parent)
            channel_frame.setGeometry(0, y, 340, 24)

            # channel number
            channel_text = QtWidgets.QLabel(channel_frame)
            channel_text.setGeometry(x_positions[0], 2, 25, 18)
            channel_text.setText(channel)

            # check box
            channel_active_check_box = QtWidgets.QCheckBox(channel_frame)
            channel_active_check_box.setGeometry(x_positions[1], 2, 18, 18)

            # initial value
            channel_initial_spin_box = QtWidgets.QDoubleSpinBox(channel_frame)
            channel_initial_spin_box.setGeometry(x_positions[2], 2, 68, 18)
            channel_initial_spin_box.setDecimals(4)
            channel_initial_spin_box.setMaximum(1.0)
            channel_initial_spin_box.setValue(configuration.get("starting_value"))
            channel_initial_spin_box.setSingleStep(0.0001)

            # increment
            channel_inc_spin_box = QtWidgets.QDoubleSpinBox(channel_frame)
            channel_inc_spin_box.setGeometry(x_positions[3], 2, 68, 18)
            channel_inc_spin_box.setDecimals(4)
            channel_inc_spin_box.setValue(configuration.get("increment"))
            channel_inc_spin_box.setSingleStep(0.0001)

            # time to increment
            channel_time_spin_box = QtWidgets.QSpinBox(channel_frame)
            channel_time_spin_box.setGeometry(x_positions[4], 2, 68, 18)
            channel_time_spin_box.setMinimum(100)
            channel_time_spin_box.setMaximum(100000)
            channel_time_spin_box.setValue(configuration.get("frames"))
            channel_time_spin_box.setSingleStep(100)
            
            self.channels.append([channel_active_check_box,
                                  channel_initial_spin_box,
                                  channel_inc_spin_box,
                                  channel_time_spin_box])

            y += dy

        self.height = y

    def remoteSetChannel(self, which_channel, initial, inc, time):
        """
        This is called by an external program to specify the
        settings for a particular channel.
        """
        channel = self.channels[which_channel]
        channel[0].setChecked(True)
        channel[1].setValue(initial)
        channel[2].setValue(inc)
        channel[3].setValue(time)

    def startFilm(self):
        """
        This is called when the filming starts. It returns the
        desired initial powers for the various channels.
        """
        for i, channel in enumerate(self.channels):
            self.which_checked[i] = False
            self.powers[i] = (float(channel[1].value()))
            if channel[0].isChecked():
                self.which_checked[i] = True
        return [self.which_checked, self.powers]

    def stopFilm(self):
        """
        This is called when the film stops. It resets the powers
        to their initial values.
        """
        for i, channel in enumerate(self.channels):
            self.powers[i] = (float(channel[1].value()))
        return [self.which_checked, self.powers]


class LinearChannels(MathChannels):
    """
    Channels class for linear progression.
    """
    def __init__(self, channels = None, **kwds):
        """
        This is basically the same as for MathChannels. It also specifies
        a maximum value for the increment spin box.
        """
        kwds["channels"] = channels
        super().__init__(**kwds)
        for channel in self.channels:
            channel[2].setMaximum(1.0)

    def handleNewFrame(self, frame_number):
        """
        Called when we get a new frame from the camera. Returns the which
        channels (if any) need to have their power adjusted.
        """
        active = []
        increment = []
        for i, channel in enumerate(self.channels):
            if self.which_checked[i] and ((frame_number % channel[3].value()) == 0):
                active.append(True)
                increment.append(float(channel[2].value()))
            else:
                active.append(False)
                increment.append(float(channel[2].value()))
        return [active, increment]


class ExponentialChannels(MathChannels):
    """
    Channels class for exponential progression.
    """
    def __init__(self, channels = None, **kwds):
        """
        This is basically the same as for MathChannels. It also specifies
        the current and maximum value of the increment spin box.
        """
        kwds["channels"] = channels
        super().__init__(**kwds)
        for channel in self.channels:
            channel[2].setValue(1.05)
            channel[2].setMaximum(9.9)

    def handleNewFrame(self, frame_number):
        """
        Called when we get a new frame from the camera. Returns the which
        channels (if any) need to have their power adjusted.
        """
        active = []
        increment = []
        for i, channel in enumerate(self.channels):
            if self.which_checked[i] and ((frame_number % channel[3].value()) == 0):
                active.append(True)
                new_power = float(channel[2].value()) * self.powers[i]
                inc = new_power - self.powers[i]
                increment.append(inc)
                self.powers[i] = new_power
            else:
                active.append(False)
                increment.append(float(channel[2].value()))
        return [active, increment]


class FileChannels(Channels):
    """
    Channels class for power file bases progression. This lets you
    replay the power settings that you used in previous films.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.active = []
        self.start_powers = []
        self.file_ptr = False

    def getNextPowers(self):
        """
        Read and parse the next line of the powers file, or False 
        if we have reached the end of the file.
        """
        line = self.file_ptr.readline()
        powers = False
        if line:
            powers = []
            powers_text = line.split(" ")[1:]
            for i in range(len(powers_text)):
                powers.append(float(powers_text[i]))
        return powers

    def handleNewFrame(self, frame_number):
        """
        Called when we get a new frame from the camera. Returns the which
        channels (if any) need to have their power adjusted.
        """
        if self.file_ptr:
            powers = self.getNextPowers()
            active = []
            increment = []
            if powers:
                for i in range(len(powers)):
                    if powers[i] != self.powers[i]:
                        active.append(True)
                        increment.append(powers[i] - self.powers[i])
                        self.powers[i] = powers[i]
                    else:
                        active.append(False)
                        increment.append(False)
            return [active, increment]
        else:
            return [[], []]

    def newFile(self, filename):
        """
        Open a powers file & read the first line to 
        get the initial power values.
        """
        # FIXME: Shouldn't this just fail if the file does not exist?
        if os.path.exists(filename):
            self.file_ptr = open(filename, "r")
            self.file_ptr.readline()
            self.active = []
            self.start_powers = []
            powers = self.getNextPowers()
            if powers:
                for power in powers:
                    self.active.append(True)
                    self.powers.append(power)
                    self.start_powers.append(power)
        else:
            self.file_ptr = False

    def startFilm(self):
        """
        This is called when the filming starts. It returns the
        desired initial powers for the various channels. It also
        rewinds the file pointer to beginning of the powers file.
        """
        if self.file_ptr:
            # reset file ptr
            self.file_ptr.seek(0)
            self.file_ptr.readline()
            # reset internal power record
            for i in range(len(self.start_powers)):
                self.powers[i] = self.start_powers[i]
            return [self.active, self.start_powers]
        else:
            return [[], []]

    def stopFilm(self):
        """
        This is called when the film stops. It resets the powers
        to their initial values.
        """
        if self.file_ptr:
            return [self.active, self.start_powers]
        else:
            return [[], []]


class ProgressionsView(halDialog.HalDialog):
    """
    Progression control dialog box
    """
    def __init__(self, configuration = None, **kwds):
        """
        This initializes things and sets up the UI 
        of the power control dialog box.
        """
        super().__init__(**kwds)

        self.channels = False
        self.configuration = configuration
        self.directory = None
        self.exp_channels = None
        self.ilm_functionality = None
        self.linear_channels = None
        self.file_channels = None
        self.parameters = params.StormXMLObject()
        self.use_was_checked = False
        self.which_checked = []

        # Add progression parameters.
        self.parameters.add(params.ParameterSetBoolean(name = "use_progressions",
                                                       value = False,
                                                       is_mutable = False))
        
        self.parameters.add(params.ParameterStringFilename(description = "Progression file name",
                                                           name = "pfile_name",
                                                           value = "",
                                                           use_save_dialog = False))

        # UI setup
        self.ui = progressionUi.Ui_Dialog()
        self.ui.setupUi(self)

        self.ui.loadFileButton.clicked.connect(self.handleLoadFile)
        self.ui.progressionsCheckBox.stateChanged.connect(self.handleProgressionsCheck)

    def getParameters(self):
        return self.parameters
    
    def handleLoadFile(self, boolean):
        """
        Opens a file dialog where the user can specify a new power file.
        """
        power_filename = QtWidgets.QFileDialog.getOpenFileName(self,
                                                               "New Power File",
                                                               self.directory,
                                                               "*.power")[0]
        if power_filename:
            self.parameters.setv("pfile_name", power_filename)
            self.ui.filenameLabel.setText(power_filename[-40:])
            self.file_channels.newFile(power_filename)
            
    def handleNewFrame(self, frame, filming):
        """
        This is called when we get new frames from the camera. It
        calls the newFrame method of the active channels object.
        If this returns that power updates are necessary then it
        emits the appropriate progIncPower signals.
        """
        if filming and self.channels and frame.master:
            if (frame.number > 0):
                [active, increment] = self.channels.newFrame(frame.number)
                for i in range(len(active)):
                    if active[i]:
                        self.incPower.emit(int(i), increment[i])

    def handleProgressionsCheck(self, state):
        """
        This is called when the user clicks the progression check box.
        """
        self.parameters.setv("use_progressions", bool(state))

    def haveFunctionality(self):
        return self.ilm_functionality is not None

    def newParameters(self, parameters):
        """
        This is called when there are new parameters. Note that there are
        no parameter specific settings for all the GUI elements. This
        just checks / unchecks the use progressions check box.
        """
        self.ui.progressionsCheckBox.setChecked(parameters.get("use_progressions"))

        self.parameters.setv("pfile_name", parameters.get("pfile_name"))
        power_filename = self.parameters.get("pfile_name")
        self.ui.filenameLabel.setText(power_filename[-40:])
        self.file_channels.newFile(power_filename)

    def setDirectory(self, directory):
        self.directory = directory
        
    def setFunctionality(self, functionality):
        """
        Configure the illumination channels using the illumination functionality.
        """
        self.ilm_functionality = functionality

        channels = self.ilm_functionality.getChannelNames()
        
        self.which_checked = []
        for i in range(len(channels)):
            self.which_checked.append(False)

        # Linear increasing power tab setup.
        self.linear_channels = LinearChannels(channels = channels,
                                              configuration = self.configuration,
                                              x_positions = [self.ui.channelLabel.pos().x(),
                                                             self.ui.activeLabel.pos().x(),
                                                             self.ui.startLabel.pos().x(),
                                                             self.ui.incrementLabel.pos().x(),
                                                             self.ui.framesLabel.pos().x()],
                                              parent = self.ui.linearTab)

        # Exponential increasing power tab setup.
        self.exp_channels = ExponentialChannels(channels = channels,
                                                configuration = self.configuration,
                                                x_positions = [self.ui.channelLabel_2.pos().x(),
                                                               self.ui.activeLabel_2.pos().x(),
                                                               self.ui.startLabel_2.pos().x(),
                                                               self.ui.incrementLabel_2.pos().x(),
                                                               self.ui.framesLabel_2.pos().x()],
                                                parent = self.ui.expTab)

        # Increment power as specified in a file.
        self.file_channels = FileChannels()

#        # adjust overall size to match number of channels
#        y = self.linear_channels.height + 65
#        old_width = self.ui.progressionsBox.width()
#        self.ui.progressionsBox.setGeometry(10, 0, old_width, y + 2)
#
#        self.ui.okButton.setGeometry(old_width - 65, y + 5, 75, 24)
#        self.ui.progressionsCheckBox.setGeometry(2, y + 7, 151, 18)
#
#        self.setFixedSize(self.width(), y + 36)
        
    def setInitialPower(self, active, power):
        """
        This emits progSetPower signals to set the power. This 
        is called at the start & end of filming.
        """
        for i in range(len(active)):
            if active[i]:
                self.setPower.emit(int(i), power[i])

    def startFilm(self):
        """
        Called at the start of filming. If the progression dialog is
        open and the use progressions check box is checked it figures 
        out which tab is visible to determine which is the active channel
        object. Then it sets the intial powers as specified by the
        active channel.
        """
        self.channels = False
        if (self.isVisible() and self.parameters.get("use_progressions")):
            # determine which tab is active.
            if self.ui.linearTab.isVisible():
                self.channels = self.linear_channels
            elif self.ui.expTab.isVisible():
                self.channels = self.exp_channels
            elif self.ui.fileTab.isVisible():
                self.channels = self.file_channels
            [active, power] = self.channels.startFilm()
            self.setInitialPower(active, power)

    def stopFilm(self):
        """
        Called when the film stops. This resets the 
        powers to their initial values.
        """
        if self.channels:
            [active, power] = self.channels.stopFilm()
            self.setInitialPower(active, power)
        if self.use_was_checked:
            self.use_was_checked = False
            self.ui.progressionsCheckBox.setChecked(True)


class Progressions(halModule.HalModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)

        configuration = module_params.get("configuration")
        self.ilm_fn_name = configuration.get("illumination_functionality")

        self.view = ProgressionsView(configuration = configuration,
                                     module_name = self.module_name)
        self.view.halDialogInit(qt_settings,
                                module_params.get("setup_name") + " progression control")

        # Unhide stage control.
        halMessage.addMessage("show progressions",
                              validator = {"data" : None, "resp" : None})
        
    def cleanUp(self, qt_settings):
        self.view.cleanUp(qt_settings)

    def handleResponse(self, message, response):
        if message.isType("get functionality"):
            self.view.setFunctionality(response.getData()["functionality"])
            self.sendMessage(halMessage.HalMessage(m_type = "add to menu",
                                                   data = {"item name" : "Progressions",
                                                           "item msg" : "show progressions"}))

    def processMessage(self, message):
            
        if message.isType("configure1"):
            self.sendMessage(halMessage.HalMessage(m_type = "get functionality",
                                                   data = {"name" : self.ilm_fn_name}))

            self.sendMessage(halMessage.HalMessage(m_type = "initial parameters",
                                                   data = {"parameters" : self.view.getParameters()}))

        elif message.isType("new directory"):
            self.view.setDirectory(message.getData()["directory"])
            
        elif message.isType("new parameters"):
            p = message.getData()["parameters"]
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"old parameters" : self.view.getParameters().copy()}))
            self.view.newParameters(p.get(self.module_name))
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"new parameters" : self.view.getParameters()}))
            
        elif message.isType("show progressions"):
            self.view.show()

        elif message.isType("start"):
            if message.getData()["show_gui"] and self.view.haveFunctionality():
                self.view.showIfVisible()

        elif message.isType("stop film"):
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"parameters" : self.view.getParameters()}))


    ## tcpHandleProgressionFile
    #
    # Handles TCP/IP signal to set the power
    # file for file based power progressions.
    #
    # @param filename The filename of the power file.
    #
#    @hdebug.debug
#    def tcpHandleProgressionFile(self, filename):
#        if os.path.exists(filename):
#            self.ui.filenameLabel.setText(filename[-40:])
#            self.file_channels.newFile(filename)
        
    ## tcpHandleProgressionSet
    #
    # Handles TCP/IP signal to set the values of a math channel.
    #
    # @param channel The channel number.
    # @param start_power The starting power.
    # @param frames The number of frames between increments.
    # @param increment The amount to increments.
    #
#    @hdebug.debug
#    def tcpHandleProgressionSet(self, channel, start_power, frames, increment):
#        if frames is None:
#            frames = 100
#        if increment is None:
#            increment = 0.0
#        if self.ui.linearTab.isVisible():
#            self.linear_channels.remoteSetChannel(channel, start_power, increment, frames)
#        elif self.ui.expTab.isVisible():
#            self.exp_channels.remoteSetChannel(channel, start_power, increment, frames)

    ## tcpHandleProgressionLockout
    #
    # Handles TCP/IP signal to lockout progressions.
    #
#    def tcpHandleProgressionLockout(self):
#        self.use_was_checked = self.ui.progressionsCheckBox.isChecked()
#        self.ui.progressionsCheckBox.setChecked(False)

    ## tcpHandleProgressionType
    #
    # Handles TCP/IP signal to set the progression type.
    #
    # @param type This is one of "linear", "exponential" or "file"
    #
#    @hdebug.debug
#    def tcpHandleProgressionType(self, type):
#        self.show()
#        self.ui.progressionsCheckBox.setChecked(True)
#        if (type == "linear"):
#            self.ui.tabWidget.setCurrentWidget(self.ui.linearTab)
#        elif (type == "exponential"):
#            self.ui.tabWidget.setCurrentWidget(self.ui.expTab)
#        elif (type == "file"):
#            self.ui.tabWidget.setCurrentWidget(self.ui.fileTab)


#
# The MIT License
#
# Copyright (c) 2014 Zhuang Lab, Harvard University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#