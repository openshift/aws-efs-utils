use thiserror::Error as ThisError;

use crate::aws::s3_client::S3ClientError;

#[derive(Debug, ThisError)]
pub enum ReadAheadCacheError {
    /// The cache entry went away before the read could copy out of it. Retryable.
    #[error("Data evicted before read completed")]
    DataEvicted,
    /// The memory pool has no room for the chunks this read needs.
    #[error("Memory pool at capacity")]
    MemoryPoolAtCapacity,
    /// Failure that has no dedicated variant yet.
    #[error("{0}")]
    Other(String),
}

/// Failure returned by the readahead cache's read path. `s3_error` and `cache_error` let the
/// caller pick a retry policy without parsing `message`.
#[derive(Debug, ThisError)]
#[error("ReadAhead error: {message}")]
pub struct ReadAheadError {
    /// Human-readable description of the failure, for callers that only log it.
    pub message: String,
    pub s3_error: Option<S3ClientError>,
    pub cache_error: Option<ReadAheadCacheError>,
}

impl From<ReadAheadCacheError> for ReadAheadError {
    fn from(error: ReadAheadCacheError) -> Self {
        Self {
            message: error.to_string(),
            s3_error: None,
            cache_error: Some(error),
        }
    }
}

impl From<S3ClientError> for ReadAheadError {
    fn from(error: S3ClientError) -> Self {
        Self {
            message: format!("S3 read failed: {}", error),
            s3_error: Some(error),
            cache_error: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_error_conversion_keeps_variant() {
        let error: ReadAheadError = ReadAheadCacheError::DataEvicted.into();
        assert!(matches!(
            error.cache_error,
            Some(ReadAheadCacheError::DataEvicted)
        ));
        assert!(error.s3_error.is_none());
        assert_eq!(error.message, "Data evicted before read completed");
    }

    #[test]
    fn test_other_cache_error_conversion() {
        let error: ReadAheadError =
            ReadAheadCacheError::Other("Cache entry failed to load".to_string()).into();
        assert!(matches!(
            error.cache_error,
            Some(ReadAheadCacheError::Other(_))
        ));
        assert_eq!(error.message, "Cache entry failed to load");
    }

    #[test]
    fn test_s3_error_conversion_keeps_error_class() {
        let error: ReadAheadError = S3ClientError::Throttled.into();
        assert!(matches!(error.s3_error, Some(S3ClientError::Throttled)));
        assert!(error.cache_error.is_none());
    }
}
