import argparse
import os
import time
from threading import Thread
from subprocess import call

import numpy as np
import pvporcupine
import soundfile
from pvrecorder import PvRecorder

import RPi.GPIO as GPIO


class MicrophoneListener(Thread):
    """
    Objects of this class will listen to one microphone.
    """
    def __init__(
        self,
        library_path,
        model_path,
        keyword_path,
        sensitivity,
        input_device_index,
        input_device_name,
        output_path=None):
        """
        Constructor of the listener.

        :param library_path: Absolute path to Porcupine's dynamic library.
        :param model_path: Absolute path to the file containing model parameters.
        :param keyword_paths: Absolute paths to keyword model files.
        :param sensitivity: Sensitivity for detecting keywords. Each value should be a number within [0, 1]. A
        higher sensitivity results in fewer misses at the cost of increasing the false alarm rate. If not set 0.5 will
        be used.
        :param input_device_index: Audio is recorded from this input device.
        :param input_device_name: Audio is recorded from this input device.        
        :param output_path: If provided recorded audio will be stored in this location at the end of the run.
        """

        super(MicrophoneListener, self).__init__()

        self._library_path = library_path
        self._model_path = model_path
        self._keyword_paths = keyword_path
        self._sensitivity = sensitivity
        self._input_device_index = input_device_index
        self.input_device_name = input_device_name

        self._output_path = output_path
        if self._output_path is not None:
            self._recorded_frames = []

        self.shoot_requested = False
        self.time_of_last_shoot_request = 0.0
        # Start a thread to listen to the microphone.
        self.running = None
        self.porcupine = None
        self.recorder = None
        try:
            self.porcupine = pvporcupine.create(
                library_path=self._library_path,
                model_path=self._model_path,
                keyword_paths=self._keyword_paths,
                sensitivities=[self._sensitivity])
            self.recorder = PvRecorder(
                device_index=self._input_device_index, 
                frame_length=self.porcupine.frame_length)
            self.recorder.start()
            self.running = True
            self.thread_listening = Thread(target=self.run)
            self.thread_listening.start()
        except Exception as e:
            print('Can not create a listener for "' + self.input_device_name + '"')
            print(e)
            self.stop_listening()

    def run(self):
        while (self.running):
            try: 
                pcm = self.recorder.read()
            except:
                # No audio device connected or an error occured.
                # Terminate this microphone listener.
                self.running = False
                break
            if self._output_path is not None:
                self._recorded_frames.append(pcm)
            result = self.porcupine.process(pcm)
            if (result >= 0):
                self.shoot_requested = True
                self.time_of_last_shoot_request = time.time()

    def stop_listening(self):
        """
        This function stops the listening-thread.
        Note that if an error occurs the run-function of this class
        will automatically call this function.
        Otherwise you can also call this function from the MicrophoneHandler.
        """
        if self.porcupine is not None:
            try:
                self.porcupine.delete()
            except:
                pass

        if self.recorder is not None:
            try:
                self.recorder.delete()
            except:
                pass

        if self._output_path is not None and len(self._recorded_frames) > 0:
            recorded_audio = np.concatenate(self._recorded_frames, axis=0).astype(np.int16)
            soundfile.write(
                self._output_path, 
                recorded_audio, 
                samplerate=self.porcupine.sample_rate, 
                subtype='PCM_16')
        
        self.running = False
        try:
            self.thread_listening.join()
        except:
            print('Error while stopping the thread.')




class MicrophoneHandler(Thread):
    """
    This class keeps track of all connected (or disconnected) microphones and triggers the shot.
    """
    def __init__(
        self,
        library_path,
        model_path,
        keyword_paths,
        sensitivity,
        output_path=None):
        """
        Constructor. This defines the settings, the MicrophoneListeners will get.

        :param library_path: Absolute path to Porcupine's dynamic library.
        :param model_path: Absolute path to the file containing model parameters.
        :param keyword_paths: Absolute paths to keyword model files.
        :param sensitivity: Sensitivity for detecting keywords. Each value should be a number within [0, 1]. A
        higher sensitivity results in fewer misses at the cost of increasing the false alarm rate. If not set 0.5 will
        be used.
        :param output_path: If provided recorded audio will be stored in this location at the end of the run.
        """

        print('Creating MicrophoneHandler ...')

        super(MicrophoneHandler, self).__init__()

        # Initialize the Porcupine settings.
        self._library_path = library_path
        self._model_path = model_path
        self._keyword_paths = keyword_paths
        self._sensitivity = sensitivity
        self._output_path = output_path
        if self._output_path is not None:
            self._recorded_frames = []
        keywords = list()
        for x in self._keyword_paths:
            keyword_phrase_part = os.path.basename(x).replace('.ppn', '').split('_')
            if len(keyword_phrase_part) > 6:
                keywords.append(' '.join(keyword_phrase_part[0:-6]))
            else:
                keywords.append(keyword_phrase_part[0])

        # Initialize the Raspberry Pi GPIOs.
        self.pin_led_shoot = 5
        self.pin_led_microphone = 6
        self.pin_led_running = 13
        self.pin_shoot = 26
        self.pin_poweroff_request = 17
        self.pin_shoot_request = 27
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.pin_led_shoot, GPIO.OUT)  # fire led.
        GPIO.output(self.pin_led_shoot, 0)
        GPIO.setup(self.pin_led_microphone, GPIO.OUT)  # mic led.
        GPIO.output(self.pin_led_microphone, 0)
        GPIO.setup(self.pin_led_running, GPIO.OUT) # running led.
        GPIO.output(self.pin_led_running, 1)
        GPIO.setup(self.pin_shoot, GPIO.OUT) # fire shot.
        GPIO.output(self.pin_shoot, 0)
        GPIO.setup(self.pin_poweroff_request , GPIO.IN) # poweroff button.
        GPIO.add_event_detect(self.pin_poweroff_request , GPIO.FALLING, 
            callback=self.poweroff, bouncetime=100)
        GPIO.setup(self.pin_shoot_request, GPIO.IN) # fire button.
        GPIO.add_event_detect(self.pin_shoot_request, GPIO.FALLING, 
            callback=self.manual_shoot_request, bouncetime=100)

        self.microphones = []
        self.manual_shoot_request = False
        self.time_of_last_manual_shoot_request = 0.0
        self.time_of_last_shoot_request = 0.0
        self.time_difference_between_shots = 2.0 # seconds

        GPIO.output(self.pin_led_running, 1)
        print('MicrophoneHandler created. Start the loop.')
        self.run()

    def poweroff(self, _):
        """
        This function is triggered by a button connected to the Raspberry Pi GPIO.
        It will poweroff the Raspberry Pi.
        """
        for microphone in self.microphones:
            if microphone.running == True:
                microphone.stop_listening()
        GPIO.cleanup()
        call("sudo shutdown -h now", shell=True)

    def manual_shoot_request(self, _):
        """
        This function is triggered by a button connected to the Raspberry Pi GPIO.
        It will save a manual shoot request.
        """
        self.manual_shoot_request = True
        self.time_of_last_manual_shoot_request = time.time()

    def clean_up_microphones(self):
        """
        This function checks, what microphones are not in use anymore and removes them.
        """
        for microphone in self.microphones:
            if microphone.running == False:
                print('Lost microphone "' + microphone.input_device_name + '"')
                microphone.stop_listening()
        self.microphones = [mic for mic in self.microphones if mic.running == True]

    def check_for_new_microphones(self):
        """
        This function checks, whether a new microphone is connected.
        """
        try:
            connected_microphones = PvRecorder.get_audio_devices()
        except:
            print('Error: Can not read microphones using PvRecorder.')
            return
        registered_microphones = [microphone.input_device_name for microphone in self.microphones]
        # Check what microphone is currently not registered and create a new instance.
        for index_microphone, name_microphone in enumerate(connected_microphones):
            if ('Monitor of' in name_microphone) or (name_microphone in ['Discard all samples (playback) or generate zero samples (capture)', 'JACK Audio Connection Kit', 'PulseAudio Sound Server']):
                # Do not use "Monitor of ..." devices and also other drivers / kits available on the Raspberry Pi.
                continue
            if name_microphone not in registered_microphones:
                # Create a new microphone-listener.
                print('Creating listener for "' + name_microphone + '"')
                self.microphones.append(
                    MicrophoneListener(
                        self._library_path,
                        self._model_path,
                        self._keyword_paths,
                        self._sensitivity,
                        index_microphone,
                        name_microphone,
                        self._output_path
                    )
                )

    def fire(self):
        """
        This function sends a signal to the remote control.
        """
        print('Fire!')
        GPIO.output(self.pin_led_shoot, 1)
        GPIO.output(self.pin_shoot, 1)
        time.sleep(0.5)
        GPIO.output(self.pin_led_shoot, 0)
        GPIO.output(self.pin_shoot, 0)

    def run(self):
        """
        This function checks for old or new microphones and if there is a shoot request.
        """
        while (True):
            try:
                self.clean_up_microphones()
                self.check_for_new_microphones()
                if len(self.microphones) > 0:
                    GPIO.output(self.pin_led_microphone, 1)
                else:
                    GPIO.output(self.pin_led_microphone, 0)
                if self.manual_shoot_request == True:
                    if abs(self.time_of_last_manual_shoot_request - self.time_of_last_shoot_request) >= self.time_difference_between_shots:
                        self.time_of_last_shoot_request = time.time()
                        self.fire()
                    self.manual_shoot_request = False
                for microphone in self.microphones:
                    if microphone.shoot_requested == True:
                        if abs(microphone.time_of_last_shoot_request - self.time_of_last_shoot_request) >= self.time_difference_between_shots:
                            self.time_of_last_shoot_request = time.time()
                            self.fire()
                        microphone.shoot_requested = False
                time.sleep(0.2)
            except KeyboardInterrupt:
                print('Stopping ...')
                break
            except:
                print('An error occured in MicrophoneHandler.run().')
                break
        for microphone in self.microphones:
            try:
                microphone.stop_listening()
            except:
                print('Error occured while terminating microphone "' + microphone.input_device_name + '"')
        GPIO.cleanup()
        
        


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--keywords',
        nargs='+',
        help='List of default keywords for detection. Available keywords: %s' % ', '.join(sorted(pvporcupine.KEYWORDS)),
        choices=sorted(pvporcupine.KEYWORDS),
        metavar='',
        default=['computer'])

    parser.add_argument(
        '--keyword_paths',
        nargs='+',
        help="Absolute paths to keyword model files. If not set it will be populated from `--keywords` argument")

    parser.add_argument(
        '--library_path', 
        help='Absolute path to dynamic library.', 
        default=pvporcupine.LIBRARY_PATH)

    parser.add_argument(
        '--model_path',
        help='Absolute path to the file containing model parameters.',
        default=pvporcupine.MODEL_PATH)

    parser.add_argument(
        '--sensitivity',
        nargs='+',
        help="Sensitivity for detecting keywords. The value should be a number within [0, 1]. A higher " +
             "sensitivity results in fewer misses at the cost of increasing the false alarm rate. If not set 0.5 " +
             "will be used.",
        type=float,
        default=1.0)
    
    parser.add_argument(
        '--output_path', 
        help='Absolute path to recorded audio for debugging.', 
        default=None)

    args = parser.parse_args()

    if args.keyword_paths is None:
        if args.keywords is None:
            raise ValueError("Either `--keywords` or `--keyword_paths` must be set.")
        keyword_paths = [pvporcupine.KEYWORD_PATHS[x] for x in args.keywords]
    else:
        keyword_paths = args.keyword_paths

    MicrophoneHandler(
        library_path=args.library_path,
        model_path=args.model_path,
        keyword_paths=keyword_paths,
        sensitivity=args.sensitivity,
        output_path=args.output_path)


if __name__ == '__main__':
    print('Starting SSP ...')
    main()