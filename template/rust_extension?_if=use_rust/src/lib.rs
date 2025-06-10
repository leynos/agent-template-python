#![allow(non_local_definitions)]

use data_encoding::{Encoding, Specification};
use once_cell::sync::Lazy;
use pyo3::basic::CompareOp;
use pyo3::exceptions::PyValueError;
use pyo3::once_cell::GILOnceCell;
use pyo3::prelude::*;
use pyo3::pycell::PyRef;
use pyo3::types::{PyAny, PyBytes, PyDict, PyModule, PyString, PyType};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use uuid::Uuid;

#[derive(Debug)]
pub enum CrockfordError {
    InvalidLength(usize),
    DecodeError(data_encoding::DecodeError),
}

impl std::fmt::Display for CrockfordError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CrockfordError::InvalidLength(len) => write!(f, "expected 16 bytes, got {len}"),
            CrockfordError::DecodeError(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for CrockfordError {}

static CROCKFORD: Lazy<Encoding> = Lazy::new(|| {
    let mut spec = Specification::new();
    spec.symbols.push_str("0123456789ABCDEFGHJKMNPQRSTVWXYZ");
    // Accept lowercase input for all allowed characters.
    spec.translate.from = "abcdefghjkmnpqrstvwxyz".into();
    spec.translate.to = "ABCDEFGHJKMNPQRSTVWXYZ".into();
    // Handle visually similar characters per Crockford spec.
    spec.translate.from.push_str("ilILoO");
    spec.translate.to.push_str("111100");
    spec.ignore.push('-');
    spec.encoding().unwrap()
});

// Cache the 'uuid' module to avoid repeated imports at runtime.
fn uuid_module(py: Python<'_>) -> PyResult<&PyModule> {
    static UUID_MODULE: GILOnceCell<Py<PyModule>> = GILOnceCell::new();
    let module =
        UUID_MODULE.get_or_try_init(py, || PyModule::import(py, "uuid").map(|m| m.into()))?;
    Ok(module.as_ref(py))
}

pub fn encode_bytes_to_crockford(bytes: &[u8; 16]) -> String {
    CROCKFORD.encode(bytes)
}

pub fn decode_crockford_to_bytes(s: &str) -> Result<[u8; 16], CrockfordError> {
    let decoded = CROCKFORD
        .decode(s.as_bytes())
        .map_err(CrockfordError::DecodeError)?;
    if decoded.len() != 16 {
        return Err(CrockfordError::InvalidLength(decoded.len()));
    }
    let mut out = [0u8; 16];
    out.copy_from_slice(&decoded);
    Ok(out)
}

#[pyfunction]
fn encode_crockford(b: &[u8]) -> PyResult<String> {
    if b.len() != 16 {
        return Err(PyValueError::new_err(format!(
            "expected 16 bytes, got {}",
            b.len()
        )));
    }
    let arr: &[u8; 16] = b.try_into().unwrap();
    Ok(encode_bytes_to_crockford(arr))
}

#[pyfunction]
fn decode_crockford(py: Python<'_>, s: &str) -> PyResult<Py<PyBytes>> {
    let bytes = decode_crockford_to_bytes(s).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(PyBytes::new(py, &bytes).into())
}

#[pyclass]
struct CrockfordUUID {
    bytes: [u8; 16],
}

#[pymethods]
#[allow(non_local_definitions)]
impl CrockfordUUID {
    #[new]
    fn new(value: &PyAny) -> PyResult<Self> {
        if let Ok(s) = value.downcast::<PyString>() {
            let bytes = decode_crockford_to_bytes(s.to_str()?)
                .map_err(|e| PyValueError::new_err(e.to_string()))?;
            Ok(Self { bytes })
        } else if let Ok(b) = value.downcast::<PyBytes>() {
            let slice = b.as_bytes();
            if slice.len() != 16 {
                return Err(PyValueError::new_err(format!(
                    "expected 16 bytes, got {}",
                    slice.len()
                )));
            }
            let mut arr = [0u8; 16];
            arr.copy_from_slice(slice);
            Ok(Self { bytes: arr })
        } else {
            let uuid_mod = uuid_module(value.py())?;
            if value.is_instance(uuid_mod.getattr("UUID")?)? {
                let py_bytes: &PyBytes = value.getattr("bytes")?.extract()?;
                let slice = py_bytes.as_bytes();
                let mut arr = [0u8; 16];
                arr.copy_from_slice(slice);
                Ok(Self { bytes: arr })
            } else {
                Err(PyValueError::new_err(
                    "expected Crockford string, 16 bytes, or uuid.UUID",
                ))
            }
        }
    }

    #[getter]
    fn bytes<'py>(&self, py: Python<'py>) -> &'py PyBytes {
        PyBytes::new(py, &self.bytes)
    }

    #[getter]
    fn uuid(&self, py: Python) -> PyResult<PyObject> {
        let uuid_mod = uuid_module(py)?;
        let uuid_cls = uuid_mod.getattr("UUID")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("bytes", PyBytes::new(py, &self.bytes))?;
        uuid_cls.call((), Some(kwargs)).map(Into::into)
    }

    fn __bytes__(&self, py: Python<'_>) -> PyObject {
        PyBytes::new(py, &self.bytes).into()
    }

    fn __str__(&self) -> String {
        encode_bytes_to_crockford(&self.bytes)
    }

    fn __repr__(&self) -> String {
        format!(
            "CrockfordUUID('{}')",
            encode_bytes_to_crockford(&self.bytes)
        )
    }

    fn __hash__(&self) -> isize {
        let mut hasher = DefaultHasher::new();
        self.bytes.hash(&mut hasher);
        let mut value = hasher.finish() as isize;
        if value == -1 {
            value = -2;
        }
        value
    }

    fn __richcmp__(&self, other: PyRef<Self>, op: CompareOp, py: Python<'_>) -> PyObject {
        match op {
            CompareOp::Eq => (self.bytes == other.bytes).into_py(py),
            CompareOp::Ne => (self.bytes != other.bytes).into_py(py),
            _ => py.NotImplemented(),
        }
    }

    #[classmethod]
    fn generate_v4(_cls: &PyType) -> Self {
        let uuid = Uuid::new_v4();
        Self {
            bytes: *uuid.as_bytes(),
        }
    }

    #[classmethod]
    fn generate_v7(_cls: &PyType) -> Self {
        let uuid = Uuid::now_v7();
        Self {
            bytes: *uuid.as_bytes(),
        }
    }
}

#[pymodule]
fn _{{ package_name }}_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_crockford, m)?)?;
    m.add_function(wrap_pyfunction!(encode_crockford, m)?)?;
    m.add_class::<CrockfordUUID>()?;
    Ok(())
}
