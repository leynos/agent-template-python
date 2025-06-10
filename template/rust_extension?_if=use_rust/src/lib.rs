use pyo3::prelude::*;

#[pyfunction]
fn placeholder() -> PyResult<()> {
    Ok(())
}

#[pymodule]
fn _{{ package_name }}_rs(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(placeholder, m)?)?;
    Ok(())
}
