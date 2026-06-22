from dataclasses import asdict

from spectra_inspector.user_store_model import UserStore, updateDataStore


def test_user_store():

    us = UserStore(selected_dataset="myds")
    assert us.get_metadata() is None
    newStoreDict = updateDataStore(asdict(us), "selected_dataset", "new_ds")
    assert isinstance(newStoreDict, dict)
    newStore = UserStore(**newStoreDict)
    assert isinstance(newStore, UserStore)
    assert newStore.selected_dataset == newStoreDict["selected_dataset"]
