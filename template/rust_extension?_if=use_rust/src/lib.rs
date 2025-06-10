use pyo3::prelude::*;

#[pyfunction]
fn hello() -> &'static str {
    "hello from Rust"
}

#[pymodule]
fn _{{ package_name }}_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    Ok(())
}
