def test_streamlit_app_imports():
    import green_direct.ui.app as app

    assert callable(app.main)
