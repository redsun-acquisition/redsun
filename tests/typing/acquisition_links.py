"""Every signal and slot the acquisition stack links exists, and each slot returns nothing.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from collections.abc import Iterator

from redsun import AsPresenter, AsView, Link, Session
from redsun.presenter import AcquisitionPresenter
from redsun.view.qt.builtins import AcquisitionView


class Lab(Session):
    acquisition: AsPresenter[AcquisitionPresenter]
    acquisition_view: AsView[AcquisitionView]

    def wire(self) -> Iterator[Link]:
        yield self.acquisition_view.sig_launch, self.acquisition.launch
        yield self.acquisition_view.sig_pause, self.acquisition.pause
        yield self.acquisition_view.sig_resume, self.acquisition.resume
        yield self.acquisition_view.sig_stop, self.acquisition.stop
        yield self.acquisition_view.sig_action, self.acquisition.request_action
        yield self.acquisition_view.sig_base_dir, self.acquisition.set_base_dir
        yield self.acquisition.sig_plan_started, self.acquisition_view.set_started
        yield self.acquisition.sig_plan_done, self.acquisition_view.set_done
        yield self.acquisition.sig_plan_failed, self.acquisition_view.set_failed
        yield self.acquisition.sig_progress, self.acquisition_view.update_progress
        yield self.acquisition.sig_action_changed, self.acquisition_view.update_action
        yield (
            self.acquisition.sig_base_dir_changed,
            self.acquisition_view.update_base_dir,
        )
