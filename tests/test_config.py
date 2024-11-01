import json
import os

from redsun.toolkit.config import RedSunInstanceInfo

instance_config_path = "data"


def test_empty_info():
	"""Test empty redsun instance info."""

	config_file = os.path.join(
		os.path.dirname(__file__), instance_config_path, "empty_instance.json"
	)
	config_dict = json.load(open(config_file))
	instance = RedSunInstanceInfo(**config_dict)

	assert instance.engine == "exengine"
	assert instance.detectors == {}
	assert instance.lights == {}
	assert instance.motors == {}
	assert instance.scanners == {}


def test_detectors_info():
	"""Test the redsun instance info with detectors."""

	config_file = os.path.join(
		os.path.dirname(__file__), instance_config_path, "detector_instance.json"
	)
	config_dict = json.load(open(config_file))
	instance = RedSunInstanceInfo(**config_dict)

	assert instance.engine == "exengine"
	assert instance.detectors != {}
	assert instance.lights == {}
	assert instance.motors == {}
	assert instance.scanners == {}

	for _, mock in instance.detectors.items():
		assert mock.modelName == "MockDetectorModel"
		assert mock.vendor == "N/A"
		assert mock.serialNumber == "N/A"
		assert mock.supportedEngines == ["exengine"]
		assert mock.sensorSize == (0, 0)
		assert mock.pixelSize == (1, 1, 1)

	mocks = list(instance.detectors.values())
	assert mocks[0].modelParams == {
		"paramInt": 1,
		"paramStr": "info",
		"paramFloat": 1.0,
	}
	assert mocks[0].category == "area"
	assert mocks[0].exposureEGU == "ms"
	assert mocks[1].modelParams == {
		"paramInt": 2,
		"paramStr": "warning",
		"paramFloat": 2.0,
	}
	assert mocks[1].category == "line"
	assert mocks[1].exposureEGU == "s"


def test_motors_info():
	"""Test the redsun instance info with motors."""

	config_file = os.path.join(
		os.path.dirname(__file__), instance_config_path, "motor_instance.json"
	)
	config_dict = json.load(open(config_file))
	instance = RedSunInstanceInfo(**config_dict)

	assert instance.engine == "exengine"
	assert instance.detectors == {}
	assert instance.lights == {}
	assert instance.motors != {}
	assert instance.scanners == {}

	# inspect the motors
	for _, mock in instance.motors.items():
		assert mock.modelName == "MockMotorModel"
		assert mock.vendor == "N/A"
		assert mock.serialNumber == "N/A"
		assert mock.supportedEngines == ["exengine"]
		assert mock.category == "stepper"

	# check the model parameters
	mocks = list(instance.motors.values())
	assert mocks[0].modelParams == {
		"paramInt": 1,
		"paramStr": "info",
		"paramFloat": 1.0,
	}
	assert mocks[0].stepEGU == "μm"
	assert mocks[0].axes == ["X"]
	assert mocks[1].modelParams == {
		"paramInt": 2,
		"paramStr": "warning",
		"paramFloat": 2.0,
	}
	assert mocks[1].stepEGU == "mm"
	assert mocks[1].axes == ["X", "Y"]
